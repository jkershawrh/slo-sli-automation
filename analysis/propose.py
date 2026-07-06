#!/usr/bin/env python3
"""LLM proposal stage: generates SLO proposals from baseline evidence."""

import json
import os
import sys

from openai import OpenAI

from schemas.validate import validate, is_valid
from serialize import serialize
from consistency import check_consistency


SYSTEM_PROMPT = """\
You are an SRE expert generating SLO/SLI proposals grounded in empirical evidence.

You will receive a baseline artifact containing measured indicators for a service. \
Your job is to propose SLOs with achievable targets that include appropriate headroom \
based on the observed variance.

DIRECTIONALITY RULES (the four golden signals):
Each SLI type has a "direction of goodness" that determines the comparison operator:
- latency: LOWER is better. target_op = "lte". Target means "p99 at or below this value in ms".
- error_rate: LOWER is better. target_op = "lte". Target means "error ratio at or below this value".
- availability: HIGHER is better. target_op = "gte". Target means "availability ratio at or above this value".
- throughput: HIGHER is better. target_op = "gte". Target means "requests per second at or above this value".
- saturation: LOWER is better. target_op = "lte". Target means "resource utilization at or below this value".

You MUST set target_op correctly for each SLO. This field is required.

TARGET-SETTING RULES (incremental, achievable targets with headroom):
NEVER set a target exactly equal to the observed value. Always include margin.

For "lower is better" metrics (latency, error_rate, saturation) where target_op = "lte":
  Target should be ABOVE the observed value to provide headroom.
  - Good performance (low stddev relative to mean): target = observed + (1 to 2) * stddev
  - Poor performance (high stddev or concerning values): target = observed + 0.5 * stddev, set requires_review = true

For "higher is better" metrics (availability, throughput) where target_op = "gte":
  Target should be BELOW the observed value to provide headroom.
  - Good performance: target = observed - (1 to 2) * stddev
  - Poor performance: target at a modest incremental improvement, set requires_review = true

NEVER propose aspirational jumps (e.g., 93% availability to 99.9%). Propose incremental improvements.

Use the headroom object to document: the observed_value, the margin added, and why that margin was chosen.

MATURITY AWARENESS:
Check the SLOSCOPE_MATURITY_TIER environment context:
- "new": wide margins (2-3 stddev), conservative targets
- "growing": moderate margins (1-2 stddev), standard targets
- "mature": tight margins (0.5-1 stddev), aggressive but achievable

CONTEXT AWARENESS:
Check the SLOSCOPE_CONTEXT_TYPE environment context:
- "service": reason about API latency, error budgets, deployment impact, downstream dependencies
- "infra": reason about capacity planning, node health, resource exhaustion, blast radius

EVIDENCE-BASED RATIONALE RULES:
1. Every numeric target MUST be justified by values present in the baseline.
2. NEVER invent a metric value. Use only numbers from the baseline.
3. In the rationale, ANALYZE the data distribution:
   - Cite stddev and what it implies about stability
   - Cite the p50/p99 ratio (percentile spread) and what it implies about tail behavior
   - Cite sample count for confidence context
   - Suggest concrete next steps based on what the numbers reveal
   Example: "Latency stddev of 95ms (19% of p99) suggests moderate variability. \
The p50-to-p99 ratio of 4.2x indicates a meaningful tail. Investigate slow database \
queries or downstream timeouts before tightening below 600ms."
4. NEVER write generic advice like "investigate and fix" without referencing specific numbers.
5. If proposing a target tighter than observed, set requires_review = true with a review_reason.

REQUIRED SLOs:
Propose at minimum: one latency SLO (target_op: lte) and one availability or error_rate SLO.

BURN RATE POLICY:
Each SLO must include a burn_rate_policy with at least 2 multi-window burn-rate alert windows \
(critical and warning at minimum). Error budget must be consistent with the target.

RESPONSE FORMAT:
Respond ONLY with valid JSON. No markdown, no explanation outside the JSON.

{
  "schema_version": 2,
  "service": "<from baseline>",
  "baseline_schema_version": <from baseline schema_version>,
  "maturity_tier": "<new|growing|mature from context>",
  "slos": [
    {
      "sli_name": "string",
      "sli_type": "latency|availability|throughput|saturation|error_rate",
      "sli_definition": "description of the SLI",
      "target": number,
      "target_op": "lte or gte",
      "target_unit": "ms, ratio, percent, rps",
      "error_budget_percent": number (0-100),
      "burn_rate_policy": {
        "windows": [
          {"long_window": "1h", "short_window": "5m", "burn_rate": 14.4, "severity": "critical"},
          {"long_window": "6h", "short_window": "30m", "burn_rate": 6.0, "severity": "warning"}
        ]
      },
      "headroom": {
        "observed_value": number,
        "margin": number,
        "margin_rationale": "why this margin was chosen"
      },
      "rationale": "evidence-based analysis citing specific numbers",
      "requires_review": false,
      "review_reason": "only if requires_review is true"
    }
  ]
}
"""

MAX_RETRIES = 3


def create_client():
    """Create an OpenAI-compatible client from environment variables."""
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    if not base_url or not api_key:
        raise RuntimeError("LLM_BASE_URL and LLM_API_KEY must be set")
    return OpenAI(base_url=base_url, api_key=api_key)


def get_model():
    """Get the LLM model name from environment variables."""
    model = os.environ.get("LLM_MODEL", "")
    if not model:
        raise RuntimeError("LLM_MODEL must be set")
    return model


def propose(baseline, client=None, model=None):
    """Generate an SLO proposal from a baseline artifact using the LLM.

    Args:
        baseline: A dict conforming to baseline.schema.json.
        client: Optional OpenAI client (created from env vars if None).
        model: Optional model name (read from env var if None).

    Returns:
        A dict conforming to proposal.schema.json.

    Raises:
        RuntimeError: If the LLM fails to produce a valid proposal after retries.
    """
    validate(baseline, "baseline")

    if client is None:
        client = create_client()
    if model is None:
        model = get_model()

    maturity = os.environ.get("SLOSCOPE_MATURITY_TIER", "growing")
    context_type = os.environ.get("SLOSCOPE_CONTEXT_TYPE", "service")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Generate SLO proposals for this baseline.\n\n"
                f"Context: {context_type} (maturity: {maturity})\n\n"
                f"{json.dumps(baseline, indent=2, sort_keys=True)}"
            ),
        },
    ]

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )

        content = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        try:
            proposal = json.loads(content)
        except json.JSONDecodeError as e:
            last_error = "Invalid JSON: {}".format(e)
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Your response was not valid JSON. Error: {}\n"
                        "Please respond with ONLY valid JSON conforming to the schema.".format(
                            e
                        ),
                    }
                )
                continue
            raise RuntimeError(
                "LLM failed to produce valid JSON after {} retries. Last error: {}".format(
                    MAX_RETRIES, last_error
                )
            )

        try:
            validate(proposal, "proposal")
        except Exception as e:
            last_error = "Schema validation failed: {}".format(e)
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Your response failed schema validation: {}\n"
                        "Please fix the issues and respond with valid JSON only.".format(
                            e
                        ),
                    }
                )
                continue
            raise RuntimeError(
                "LLM failed schema validation after {} retries. Last error: {}".format(
                    MAX_RETRIES, last_error
                )
            )

        # Consistency check
        consistency_errors = check_consistency(proposal, baseline)
        if consistency_errors:
            last_error = "Consistency check failed: {}".format(
                "; ".join(consistency_errors)
            )
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": content})
                error_list = "\n".join(consistency_errors)
                messages.append(
                    {
                        "role": "user",
                        "content": "Consistency check failed:\n{}\n"
                        "Please fix and respond with valid JSON only.".format(
                            error_list
                        ),
                    }
                )
                continue
            raise RuntimeError(
                "LLM failed consistency check after {} retries. Last error: {}".format(
                    MAX_RETRIES, last_error
                )
            )

        return proposal

    raise RuntimeError(
        "LLM proposal failed after {} retries. Last error: {}".format(
            MAX_RETRIES, last_error
        )
    )


def main():
    """Read baseline from stdin, write proposal to stdout."""
    baseline = json.load(sys.stdin)
    proposal = propose(baseline)
    sys.stdout.write(serialize(proposal))


if __name__ == "__main__":
    main()
