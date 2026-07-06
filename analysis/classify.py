#!/usr/bin/env python3
"""LLM drift classification and remediation stage.

Stage two of the drift detector. Reads a drift-signal artifact (produced by
deviation.py) and sends it to an LLM for classification, severity assessment,
and remediation recommendations. Produces a drift-report artifact.

The LLM must:
- Respond with JSON-only conforming to drift-report schema
- Use only numbers present in the drift signals or baseline
- Choose a class from the fixed taxonomy
- Never emit executable actions (kubectl, YAML, etc.)
"""

import json
import os
import re
import sys

from openai import OpenAI

from schemas.validate import validate, is_valid
from serialize import serialize


# Fixed drift taxonomy
DRIFT_TAXONOMY = frozenset([
    "latency_regression", "latency_improvement",
    "error_rate_elevation", "error_rate_reduction",
    "throughput_collapse", "throughput_surge",
    "saturation_approach", "availability_drop",
    "distribution_shift", "no_significant_drift",
])

# Allowed class refinements from the dominant signal class
CONSISTENT_CLASSES = {
    "latency_regression": {"latency_regression", "distribution_shift"},
    "latency_improvement": {"latency_improvement"},
    "error_rate_elevation": {"error_rate_elevation"},
    "error_rate_reduction": {"error_rate_reduction"},
    "throughput_collapse": {"throughput_collapse"},
    "throughput_surge": {"throughput_surge"},
    "saturation_approach": {"saturation_approach"},
    "availability_drop": {"availability_drop"},
    "distribution_shift": {"distribution_shift"},
    "no_significant_drift": {"no_significant_drift"},
}

# Actuation patterns to detect and reject
ACTUATION_COMMANDS = re.compile(
    r"\b(kubectl|oc|curl|docker|helm)\b", re.IGNORECASE
)
YAML_BLOCK = re.compile(r"```(yaml|yml)\b", re.IGNORECASE)
JSON_BLOCK = re.compile(r"```json\b", re.IGNORECASE)
API_CALL_PATTERN = re.compile(
    r"\b(POST|PUT|PATCH|DELETE)\s+https?://", re.IGNORECASE
)

SYSTEM_PROMPT = """\
You are an SRE expert classifying drift in service-level indicators and proposing \
evidence-based remediation plans.

You will receive a drift-signal artifact containing deterministic deviation \
measurements for a service. Your job is to classify the drift, assess severity, \
analyze the root cause using the telemetry patterns, and propose prioritized \
remediation actions grounded in the evidence.

FIXED DRIFT TAXONOMY (choose exactly one):
- latency_regression: latency increased beyond tolerance
- latency_improvement: latency decreased beyond tolerance (positive change)
- error_rate_elevation: error rate increased beyond tolerance
- error_rate_reduction: error rate decreased beyond tolerance (positive change)
- throughput_collapse: throughput decreased beyond tolerance
- throughput_surge: throughput increased beyond tolerance
- saturation_approach: resource utilization increased beyond tolerance
- availability_drop: availability decreased beyond tolerance
- distribution_shift: mixed signals (e.g., median stable but tail diverged)
- no_significant_drift: no indicators breached their tolerance bands

SEVERITY LEVELS:
- critical: severe breach, immediate attention required (breach magnitude > 10x)
- high: significant breach, prompt investigation needed (breach magnitude 5-10x)
- medium: notable breach, monitor closely (breach magnitude 2-5x)
- low: minor breach, awareness only (breach magnitude 1-2x)
- info: no action needed, informational (no breach or positive change)

EVIDENCE-BASED ANALYSIS RULES:
1. Respond ONLY with valid JSON. No markdown, no explanation outside JSON.
2. Every numeric value you cite MUST come from the drift signals. NEVER invent a value.
3. Classification MUST be consistent with the dominant deterministic signal.
4. In likely_cause, ANALYZE the pattern of drift signals:
   - Compare p50 vs p99 deviations: if p99 breached but p50 is stable, this is a \
tail-latency issue (slow queries, timeouts) not a systemic slowdown
   - Check for correlated indicators: latency up + throughput down suggests capacity \
saturation; error rate up + latency up suggests upstream dependency failure
   - Use breach magnitude to quantify severity: "latency_p99_ms breached at 22.5x \
the band width while error_rate remained within tolerance, indicating a tail-latency \
issue isolated from request handling correctness"
   - Reference both live and baseline values with their specific numbers

REMEDIATION PLAN RULES (for negative drift):
For regression, elevation, collapse, saturation_approach, and availability_drop:
Each recommendation SHOULD include a remediation_plan with:
- priority: "immediate" for triage/containment, "short_term" for investigation, \
"long_term" for prevention
- evidence_basis: cite the specific drift signals that justify this action
- expected_impact: what improvement to expect if this action is taken
- verification_method: how to confirm the fix worked (e.g., "re-run drift detection \
after 1h, verify latency_p99_ms returns within tolerance band [300ms, 700ms]")

Structure remediation as:
1. IMMEDIATE: assess blast radius, consider rollback if recent deployment, check \
correlated services. Cite which indicators suggest the scope.
2. SHORT-TERM: investigate specific areas the telemetry points to. Use the p50/p99 \
pattern, throughput/error correlation, and saturation data to narrow the search.
3. LONG-TERM: prevent recurrence. Suggest monitoring, alerting thresholds, capacity \
planning, or architectural changes based on what the drift pattern reveals.

SLO PROMOTION RULES (for positive drift or stable performance):
For latency_improvement, error_rate_reduction, or no_significant_drift:
- Recommend updating the baseline to reflect current performance
- If indicators are well within tolerance bands, suggest tightening the SLO target
- Propose a specific new target value: current live performance + appropriate headroom
- Severity should be info or low

CONTEXT AWARENESS:
Check SLOSCOPE_CONTEXT_TYPE from the environment:
- "service": reason about API performance, deployment impact, downstream dependencies
- "infra": reason about node health, cluster capacity, resource exhaustion, blast radius

NO-ACTUATION RULES:
Recommendations must be advisory only. NEVER include:
- Shell commands (kubectl, oc, curl, docker, helm)
- YAML or JSON code blocks
- API calls (POST, PUT, PATCH, DELETE to URLs)
- Any executable action payload

RESPONSE SCHEMA:
{
  "schema_version": 1,
  "service": "<from drift signal>",
  "classification": "<from taxonomy>",
  "severity": "<critical|high|medium|low|info>",
  "likely_cause": "<evidence-based analysis citing specific numbers>",
  "recommendations": [
    {
      "action": "<advisory action>",
      "confidence": "<high|medium|low>",
      "rationale": "<citing specific drift signal values>",
      "remediation_plan": {
        "priority": "<immediate|short_term|long_term>",
        "evidence_basis": "<specific signals justifying this>",
        "expected_impact": "<what improvement to expect>",
        "verification_method": "<how to confirm the fix>"
      }
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


def extract_signal_values(drift_signal):
    """Extract all numeric values from a drift-signal artifact."""
    values = set()

    for ind in drift_signal.get("indicators", []):
        for key in [
            "live_value", "baseline_value", "abs_deviation",
            "rel_deviation", "band_upper", "band_lower",
        ]:
            val = ind.get(key)
            if isinstance(val, (int, float)):
                values.add(float(val))

    dom = drift_signal.get("dominant_signal", {})
    bm = dom.get("breach_magnitude")
    if isinstance(bm, (int, float)):
        values.add(float(bm))

    return values


def check_actuation(report):
    """Check for executable content in the report. Returns list of errors."""
    errors = []
    text_fields = [report.get("likely_cause", "")]
    for rec in report.get("recommendations", []):
        text_fields.append(rec.get("action", ""))
        text_fields.append(rec.get("rationale", ""))

    combined = " ".join(text_fields)

    match = ACTUATION_COMMANDS.search(combined)
    if match:
        errors.append(
            "Executable command detected: '{}'".format(match.group(0))
        )

    if YAML_BLOCK.search(combined):
        errors.append("YAML code block detected in response")

    if JSON_BLOCK.search(combined):
        errors.append("JSON code block detected in response")

    if API_CALL_PATTERN.search(combined):
        errors.append("API call pattern detected in response")

    return errors


def _extract_cited_numbers(text):
    """Extract numbers from text that appear to be metric value citations.

    Skips numbers that are part of:
    - Metric names preceded by a letter (e.g., p99, p50)
    - Percentages (followed by %)
    - Multipliers (followed by x)
    - Time references (followed by h or d without further letters)
    """
    result = []
    for m in re.finditer(r"-?[\d]+\.?[\d]*", text):
        num_str = m.group()
        start = m.start()
        end = m.end()

        # Skip if preceded by a letter (metric name like p99, p50)
        if start > 0 and text[start - 1].isalpha():
            continue
        # Also check before a leading negative sign
        if num_str.startswith("-") and start > 0 and text[start - 1].isalpha():
            continue

        # Skip if followed by %, x, or X (percentages and multipliers)
        if end < len(text) and text[end] in ("%", "x", "X"):
            continue

        # Skip time units (h, d) not followed by another letter
        if end < len(text) and text[end] in ("h", "d"):
            if end + 1 >= len(text) or not text[end + 1].isalpha():
                continue

        try:
            num = float(num_str)
        except ValueError:
            continue

        if num == 0:
            continue

        result.append((num, num_str))

    return result


def check_grounding(report, drift_signal):
    """Check that every number cited in the report exists in the signals.

    Returns a list of error strings (empty if grounded). Skips numbers
    that are part of metric names (p99), percentages (50%), multipliers
    (4x), or time references (24h).
    """
    signal_values = extract_signal_values(drift_signal)
    errors = []

    text_fields = [report.get("likely_cause", "")]
    for rec in report.get("recommendations", []):
        text_fields.append(rec.get("rationale", ""))

    combined = " ".join(text_fields)
    cited = _extract_cited_numbers(combined)

    for num, num_str in cited:
        grounded = False
        for sv in signal_values:
            if sv == 0:
                if abs(num) < 1e-10:
                    grounded = True
                    break
                continue
            if abs(num - sv) / max(abs(sv), 1e-10) < 0.02:
                grounded = True
                break

        if not grounded:
            errors.append(
                "Number {} not found in drift signals".format(num_str)
            )

    return errors


def check_class_consistency(report, drift_signal):
    """Check that the LLM class is consistent with the dominant signal.

    Returns a list of error strings (empty if consistent).
    """
    errors = []
    classification = report.get("classification", "")

    if classification not in DRIFT_TAXONOMY:
        errors.append(
            "Classification '{}' is not in the fixed taxonomy".format(
                classification
            )
        )
        return errors

    dominant_class = drift_signal.get("dominant_signal", {}).get("class", "")
    if dominant_class not in CONSISTENT_CLASSES:
        return errors  # unknown dominant class, allow any valid taxonomy

    if classification not in CONSISTENT_CLASSES[dominant_class]:
        errors.append(
            "Classification '{}' is inconsistent with dominant signal "
            "class '{}'. Allowed: {}".format(
                classification,
                dominant_class,
                CONSISTENT_CLASSES[dominant_class],
            )
        )

    return errors


def check_severity_consistency(report, drift_signal):
    """Check that severity is consistent with deviation magnitude.

    Returns a list of error strings (empty if consistent).
    """
    errors = []
    severity = report.get("severity", "")
    breach_mag = drift_signal.get("dominant_signal", {}).get(
        "breach_magnitude", 0
    )
    classification = report.get("classification", "")

    # Basic checks: no breaches should not be critical/high
    if breach_mag == 0 and severity in ("critical", "high"):
        errors.append(
            "Severity '{}' is too high for breach magnitude 0".format(severity)
        )

    # Large breaches should not be info
    if breach_mag > 2.0 and severity == "info":
        errors.append(
            "Severity 'info' is too low for breach magnitude {}".format(
                breach_mag
            )
        )

    # Improvement classes should not be critical
    improvement_classes = {"latency_improvement", "error_rate_reduction"}
    if classification in improvement_classes and severity in (
        "critical", "high"
    ):
        errors.append(
            "Severity '{}' is too high for improvement class '{}'".format(
                severity, classification
            )
        )

    return errors


def classify(drift_signal, client=None, model=None):
    """Classify a drift-signal artifact using the LLM.

    Args:
        drift_signal: A dict conforming to drift-signal.schema.json.
        client: Optional OpenAI client (created from env vars if None).
        model: Optional model name (read from env var if None).

    Returns:
        A dict conforming to drift-report.schema.json.

    Raises:
        RuntimeError: If the LLM fails to produce a valid report after retries.
    """
    validate(drift_signal, "drift-signal")

    if client is None:
        client = create_client()
    if model is None:
        model = get_model()

    context_type = os.environ.get("SLOSCOPE_CONTEXT_TYPE", "service")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Classify the drift and propose remediation for this "
                "drift signal.\n\n"
                "Context: {}\n\n"
                "{}".format(
                    context_type,
                    json.dumps(drift_signal, indent=2, sort_keys=True),
                )
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

        # Parse JSON
        try:
            report = json.loads(content)
        except json.JSONDecodeError as e:
            last_error = "Invalid JSON: {}".format(e)
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Your response was not valid JSON. Error: {}\n"
                    "Please respond with ONLY valid JSON conforming to the "
                    "drift-report schema.".format(e),
                })
                continue
            raise RuntimeError(
                "LLM failed to produce valid JSON after {} retries. "
                "Last error: {}".format(MAX_RETRIES, last_error)
            )

        # Schema validation
        try:
            validate(report, "drift-report")
        except Exception as e:
            last_error = "Schema validation failed: {}".format(e)
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Your response failed schema validation: {}\n"
                    "Please fix the issues and respond with valid JSON "
                    "only.".format(e),
                })
                continue
            raise RuntimeError(
                "LLM failed schema validation after {} retries. "
                "Last error: {}".format(MAX_RETRIES, last_error)
            )

        # Consistency checks
        consistency_errors = []

        # Class consistency with dominant signal
        consistency_errors.extend(
            check_class_consistency(report, drift_signal)
        )

        # Severity consistency with deviation magnitude
        consistency_errors.extend(
            check_severity_consistency(report, drift_signal)
        )

        # Grounding check
        grounding_errors = check_grounding(report, drift_signal)
        consistency_errors.extend(grounding_errors)

        # No-actuation check
        actuation_errors = check_actuation(report)
        consistency_errors.extend(actuation_errors)

        if consistency_errors:
            last_error = "Consistency check failed: {}".format(
                "; ".join(consistency_errors)
            )
            if attempt < MAX_RETRIES:
                messages.append({"role": "assistant", "content": content})
                error_list = "\n".join(consistency_errors)
                messages.append({
                    "role": "user",
                    "content": "Consistency check failed:\n{}\n"
                    "Please fix and respond with valid JSON only.".format(
                        error_list
                    ),
                })
                continue
            raise RuntimeError(
                "LLM failed consistency check after {} retries. "
                "Last error: {}".format(MAX_RETRIES, last_error)
            )

        return report

    raise RuntimeError(
        "LLM classification failed after {} retries. "
        "Last error: {}".format(MAX_RETRIES, last_error)
    )


def main():
    """Read drift-signal from stdin, write drift-report to stdout."""
    drift_signal = json.load(sys.stdin)
    report = classify(drift_signal)
    sys.stdout.write(serialize(report))


if __name__ == "__main__":
    main()
