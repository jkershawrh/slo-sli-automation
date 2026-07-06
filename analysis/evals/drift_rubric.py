"""Eval rubric for the LLM drift classification and remediation stage.

Hard gates (mandatory -- any failure is red):
1. Schema validity -- validates against drift-report schema
2. Grounding -- every cited number exists in the drift signals or baseline
3. Class validity -- class from fixed taxonomy AND consistent with dominant signal
4. No actuation -- no executable content in recommendations

Scored dimensions (all must pass for green):
1. Classification accuracy -- confirmed class matches ground truth
2. Severity calibration -- severity falls within expected range
3. Remediation relevance -- action category matches expected
4. Rationale quality -- rationale cites specific drift signal numbers
5. Remediation depth -- negative drift must have structured remediation plans
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas.validate import is_valid


# Fixed drift taxonomy
DRIFT_TAXONOMY = frozenset([
    "latency_regression", "latency_improvement",
    "error_rate_elevation", "error_rate_reduction",
    "throughput_collapse", "throughput_surge",
    "saturation_approach", "availability_drop",
    "distribution_shift", "no_significant_drift",
])

# Allowed class refinements: dominant_signal_class -> set of acceptable LLM classes.
# distribution_shift is allowed as a refinement when the dominant signal
# is a single-indicator class but mixed signal evidence exists.
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

# Actuation patterns to reject
ACTUATION_COMMANDS = re.compile(
    r"\b(kubectl|oc|curl|docker|helm)\b", re.IGNORECASE
)
YAML_BLOCK = re.compile(r"```(yaml|yml)\b", re.IGNORECASE)
JSON_BLOCK = re.compile(r"```json\b", re.IGNORECASE)
API_CALL_PATTERN = re.compile(
    r"\b(POST|PUT|PATCH|DELETE)\s+https?://", re.IGNORECASE
)

# Remediation category mapping: class -> expected category
REMEDIATION_CATEGORIES = {
    "latency_regression": "performance",
    "latency_improvement": "monitoring",
    "error_rate_elevation": "reliability",
    "error_rate_reduction": "monitoring",
    "throughput_collapse": "capacity",
    "throughput_surge": "capacity",
    "saturation_approach": "capacity",
    "availability_drop": "reliability",
    "distribution_shift": "performance",
    "no_significant_drift": "none",
}

# Keywords that identify remediation categories
CATEGORY_KEYWORDS = {
    "performance": [
        "latency", "performance", "profil", "optimiz", "regression",
        "slow", "response time", "critical path",
    ],
    "monitoring": [
        "monitor", "baseline", "update", "track", "observe",
        "sustain", "verif", "confirm",
    ],
    "reliability": [
        "error", "reliab", "fail", "log", "rollback", "deploy",
        "health", "readiness", "availab",
    ],
    "capacity": [
        "capacity", "scal", "resource", "cpu", "memory", "throughput",
        "load", "replica", "pod", "autoscal",
    ],
    "none": [
        "no action", "continue monitor", "no significant",
    ],
}


def evaluate_drift_report(report, drift_signal, ground_truth):
    """Evaluate a drift report against the rubric.

    Args:
        report: A dict (the LLM drift-report response).
        drift_signal: A dict (the drift-signal artifact input).
        ground_truth: A dict with keys "class", "severity_range",
            "remediation_category".

    Returns:
        A dict with "hard_gates", "scored_dimensions", and "pass" keys.
    """
    results = {
        "hard_gates": {},
        "scored_dimensions": {},
        "pass": False,
    }

    # Hard gate 1: Schema validity
    results["hard_gates"]["schema_validity"] = is_valid(report, "drift-report")

    # Hard gate 2: Grounding
    results["hard_gates"]["grounding"] = check_grounding(report, drift_signal)

    # Hard gate 3: Class validity and consistency
    results["hard_gates"]["class_validity"] = check_class_validity(
        report, drift_signal
    )

    # Hard gate 4: No actuation
    results["hard_gates"]["no_actuation"] = check_no_actuation(report)

    # Scored dimension 1: Classification accuracy
    results["scored_dimensions"]["classification_accuracy"] = (
        check_classification_accuracy(report, ground_truth)
    )

    # Scored dimension 2: Severity calibration
    results["scored_dimensions"]["severity_calibration"] = (
        check_severity_calibration(report, ground_truth)
    )

    # Scored dimension 3: Remediation relevance
    results["scored_dimensions"]["remediation_relevance"] = (
        check_remediation_relevance(report, ground_truth)
    )

    # Scored dimension 4: Rationale quality
    results["scored_dimensions"]["rationale_quality"] = (
        check_rationale_quality(report, drift_signal)
    )

    # Scored dimension 5: Remediation depth
    results["scored_dimensions"]["remediation_depth"] = check_remediation_depth(report, ground_truth)

    # Overall pass: all hard gates green AND all scored green
    all_hard = all(results["hard_gates"].values())
    all_scored = all(results["scored_dimensions"].values())
    results["pass"] = all_hard and all_scored

    return results


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

        result.append(num)

    return result


def check_grounding(report, drift_signal):
    """Every cited number in the report must exist in the drift signals.

    Checks likely_cause and all recommendation rationales. A number is
    considered grounded if it matches (within 2% relative tolerance) any
    numeric value in the drift-signal indicators. Numbers that are part
    of metric names (p99), percentages (50%), multipliers (4x), or time
    references (24h) are skipped.
    """
    signal_values = extract_signal_values(drift_signal)
    if not signal_values:
        return True  # nothing to ground against

    text_fields = [report.get("likely_cause", "")]
    for rec in report.get("recommendations", []):
        text_fields.append(rec.get("rationale", ""))

    combined = " ".join(text_fields)
    cited_numbers = _extract_cited_numbers(combined)

    for num in cited_numbers:
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
            return False

    return True


def check_class_validity(report, drift_signal):
    """Class must be from taxonomy and consistent with dominant signal."""
    classification = report.get("classification", "")

    # Must be a valid taxonomy member
    if classification not in DRIFT_TAXONOMY:
        return False

    # Must be consistent with dominant deterministic signal
    dominant_class = drift_signal.get("dominant_signal", {}).get("class", "")
    if dominant_class not in CONSISTENT_CLASSES:
        # Unknown dominant class -- allow any valid taxonomy member
        return True

    return classification in CONSISTENT_CLASSES[dominant_class]


def check_no_actuation(report):
    """No executable content in the report output."""
    # Collect all text fields from the report
    text_fields = [
        report.get("likely_cause", ""),
    ]
    for rec in report.get("recommendations", []):
        text_fields.append(rec.get("action", ""))
        text_fields.append(rec.get("rationale", ""))

    combined = " ".join(text_fields)

    # Check for executable command patterns
    if ACTUATION_COMMANDS.search(combined):
        return False

    # Check for YAML code blocks
    if YAML_BLOCK.search(combined):
        return False

    # Check for JSON code blocks
    if JSON_BLOCK.search(combined):
        return False

    # Check for API call patterns
    if API_CALL_PATTERN.search(combined):
        return False

    return True


def check_classification_accuracy(report, ground_truth):
    """Confirmed class must match the ground-truth label."""
    return report.get("classification") == ground_truth.get("class")


def check_severity_calibration(report, ground_truth):
    """Severity must fall within the expected range."""
    severity = report.get("severity", "")
    expected_range = ground_truth.get("severity_range", [])
    return severity in expected_range


def check_remediation_relevance(report, ground_truth):
    """Recommended actions must match the expected remediation category."""
    expected_category = ground_truth.get("remediation_category", "")

    if expected_category == "none":
        # For no-drift, any recommendation that says "continue monitoring"
        # or "no action" is appropriate
        for rec in report.get("recommendations", []):
            action = rec.get("action", "").lower()
            if any(kw in action for kw in CATEGORY_KEYWORDS["none"]):
                return True
            if any(kw in action for kw in CATEGORY_KEYWORDS["monitoring"]):
                return True
        return False

    keywords = CATEGORY_KEYWORDS.get(expected_category, [])
    if not keywords:
        return True  # no keywords to check

    # At least one recommendation must match the category
    for rec in report.get("recommendations", []):
        action = rec.get("action", "").lower()
        rationale = rec.get("rationale", "").lower()
        combined = action + " " + rationale
        if any(kw in combined for kw in keywords):
            return True

    return False


def check_remediation_depth(report, ground_truth):
    """Scored dimension: negative drift must have structured remediation plans."""
    classification = report.get("classification", "")

    # Positive drift and no-drift don't require deep remediation
    if classification in ("latency_improvement", "error_rate_reduction", "no_significant_drift"):
        return True

    # Negative drift requires at least one recommendation with remediation_plan
    recommendations = report.get("recommendations", [])
    has_plan = False
    for rec in recommendations:
        plan = rec.get("remediation_plan")
        if plan and plan.get("priority") and plan.get("evidence_basis") and plan.get("verification_method"):
            has_plan = True
            break

    return has_plan


def check_rationale_quality(report, drift_signal):
    """Each rationale must cite at least one numeric value from the signals."""
    signal_values = extract_signal_values(drift_signal)
    if not signal_values:
        return True

    for rec in report.get("recommendations", []):
        rationale = rec.get("rationale", "")
        numbers = re.findall(r"-?[\d]+\.?[\d]*", rationale)

        has_signal_ref = False
        for n in numbers:
            try:
                val = float(n)
            except ValueError:
                continue
            if val == 0:
                continue
            for sv in signal_values:
                if sv == 0:
                    continue
                if abs(val - sv) / max(abs(sv), 1e-10) < 0.02:
                    has_signal_ref = True
                    break
            if has_signal_ref:
                break

        if not has_signal_ref:
            return False

    return True
