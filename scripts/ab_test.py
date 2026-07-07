#!/usr/bin/env python3
"""A/B test: prompt variants x model variants for SLO/SLA proposal quality."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'analysis'))

from baseline import compute_baseline
from schemas.validate import is_valid
from consistency import check_consistency, EXPECTED_OPS

# --- Prompt A: current (verbose rules) ---
PROMPT_A = None  # Will use the existing SYSTEM_PROMPT from propose.py

# --- Prompt B: few-shot with worked examples ---
PROMPT_B = """\
You are an SRE expert. Given a baseline, produce SLO and SLA targets as JSON.

CRITICAL RULES:
1. Respond with ONLY valid JSON. No markdown.
2. schema_version: 3
3. Each SLO needs both slo_target (aspirational) and sla_target (commitment).

DIRECTION TABLE:
| Type         | target_op | slo_target        | sla_target           |
|-------------|-----------|-------------------|----------------------|
| latency     | lte       | BELOW observed    | ABOVE observed       |
| error_rate  | lte       | BELOW observed    | ABOVE observed       |
| availability| gte       | ABOVE observed    | BELOW observed       |
| throughput  | gte       | ABOVE observed    | BELOW observed       |
| saturation  | lte       | BELOW observed    | ABOVE observed       |

WORKED EXAMPLE:
Observed: latency p99 = 400ms, stddev = 80ms
  slo_target: 360 (400 - 0.5*80 = aim lower)
  sla_target: 480 (400 + 1*80 = ceiling with headroom)
  target_op: "lte"

Observed: availability = 0.995, error_rate stddev = 0.001
  slo_target: 0.9955 (0.995 + 0.5*0.001 = aim higher)
  sla_target: 0.993 (0.995 - 2*0.001 = floor with headroom)
  target_op: "gte"

NEVER set slo_target or sla_target equal to the observed value.
slo_target is BETWEEN observed and the improvement goal.
sla_target is BETWEEN observed and the safety margin.

Include headroom object: observed_value, margin, margin_rationale.
Include rationale citing specific baseline numbers.
Include burn_rate_policy with at least 2 windows.

{
  "schema_version": 3,
  "service": "<from baseline>",
  "baseline_schema_version": 1,
  "slos": [
    {
      "sli_name": "string",
      "sli_type": "latency|availability|error_rate|throughput|saturation",
      "sli_definition": "description",
      "slo_target": "number (aspirational)",
      "sla_target": "number (commitment)",
      "target_op": "lte or gte",
      "target_unit": "ms|ratio|rps",
      "error_budget_percent": "number 0-100",
      "burn_rate_policy": {"windows": [{"long_window":"1h","short_window":"5m","burn_rate":14.4,"severity":"critical"},{"long_window":"6h","short_window":"30m","burn_rate":6.0,"severity":"warning"}]},
      "headroom": {"observed_value": "number", "margin": "number", "margin_rationale": "string"},
      "rationale": "string citing numbers",
      "requires_review": false
    }
  ]
}
"""

# --- Models to test ---
MODELS = [
    ("granite-3-2-8b-instruct-cpu", "sk-HjSvtHOc5T1zUv1p5_ygwg", "CPU"),
    ("granite-3-2-8b-instruct",     "sk-hGlhZ_jtuPF71vs6SOFTnQ", "GPU"),
    ("granite-4-0-h-tiny",          "sk-hGlhZ_jtuPF71vs6SOFTnQ", "GPU"),
    ("microsoft-phi-4",             "sk-hGlhZ_jtuPF71vs6SOFTnQ", "GPU"),
    ("llama-scout-17b",             "sk-hGlhZ_jtuPF71vs6SOFTnQ", "GPU"),
    ("qwen3-235b",                  "sk-pwpJSxg7SDb4ygwJ0VX_nw", "API"),
]

BASE_URL = "https://maas-rhdp.apps.maas.redhatworkshops.io/v1"


def test_proposal(model, api_key, prompt, baseline):
    """Call LLM and evaluate the proposal."""
    from openai import OpenAI
    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Generate SLO proposals for this baseline.\n\nContext: service (maturity: growing)\n\n{json.dumps(baseline, indent=2, sort_keys=True)}"}
    ]

    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            timeout=120,
        )
        elapsed = time.time() - start
    except Exception as e:
        return {"status": "ERROR", "error": str(e)[:80], "elapsed": time.time() - start}

    content = response.choices[0].message.content.strip()

    # Strip markdown fences
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    # Parse JSON
    try:
        proposal = json.loads(content)
    except json.JSONDecodeError:
        return {"status": "BAD_JSON", "elapsed": elapsed}

    # Schema validation
    if not is_valid(proposal, "proposal"):
        return {"status": "SCHEMA_FAIL", "elapsed": elapsed}

    # Consistency check
    errors = check_consistency(proposal, baseline)
    if errors:
        return {"status": "CONSISTENCY_FAIL", "errors": errors[:3], "elapsed": elapsed,
                "slos": len(proposal.get("slos", []))}

    # Direction check
    direction_ok = True
    for slo in proposal.get("slos", []):
        expected = EXPECTED_OPS.get(slo.get("sli_type"))
        if expected and slo.get("target_op") != expected:
            direction_ok = False

    return {
        "status": "PASS" if direction_ok else "DIRECTION_FAIL",
        "elapsed": elapsed,
        "slos": len(proposal.get("slos", [])),
        "schema_v": proposal.get("schema_version"),
        "targets": [{
            "name": s["sli_name"],
            "type": s["sli_type"],
            "op": s["target_op"],
            "slo": s.get("slo_target"),
            "sla": s.get("sla_target"),
        } for s in proposal.get("slos", [])]
    }


def main():
    # Load baseline
    with open(os.path.join(os.path.dirname(__file__), '..', 'testdata', 'evidence_checkout_api.json')) as f:
        evidence = json.load(f)
    baseline = compute_baseline(evidence)

    # Load current prompt
    from propose import SYSTEM_PROMPT
    prompt_a = SYSTEM_PROMPT

    prompts = [("A (verbose rules)", prompt_a), ("B (few-shot examples)", PROMPT_B)]

    print("=" * 90)
    print(f"{'Model':<30} {'Tier':<5} {'Prompt':<22} {'Status':<18} {'Time':>6} {'SLOs':>4}")
    print("=" * 90)

    for model, key, tier in MODELS:
        for prompt_name, prompt in prompts:
            sys.stdout.write(f"{model:<30} {tier:<5} {prompt_name:<22} ")
            sys.stdout.flush()
            result = test_proposal(model, key, prompt, baseline)
            status = result["status"]
            elapsed = f"{result['elapsed']:.1f}s"
            slos = result.get("slos", "-")
            print(f"{status:<18} {elapsed:>6} {slos:>4}")

            if status == "PASS":
                for t in result.get("targets", []):
                    print(f"  {'':30} {'':5} {'':22} {t['name']:<18} {t['op']:>3}  SLO={t['slo']}  SLA={t['sla']}")
            elif status == "CONSISTENCY_FAIL":
                for e in result.get("errors", []):
                    print(f"  {'':30} {'':5} {'':22}   {e[:60]}")

        print("-" * 90)


if __name__ == "__main__":
    main()
