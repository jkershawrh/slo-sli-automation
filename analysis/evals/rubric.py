"""Eval rubric for the LLM proposal stage."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas.validate import is_valid
from consistency import check_consistency_bool, check_margin_quality, check_direction_validity


def evaluate_proposal(proposal, baseline):
    """Evaluate a proposal against the rubric. Returns a dict of results."""
    results = {
        "hard_gates": {},
        "scored_dimensions": {},
        "pass": False,
    }

    # Hard gate 1: Schema validity
    results["hard_gates"]["schema_validity"] = is_valid(proposal, "proposal")

    # Hard gate 2: Grounding -- every numeric target must cite a baseline value
    results["hard_gates"]["grounding"] = check_grounding(proposal, baseline)

    # Hard gate 3: Consistency -- no target tighter than observed without requires_review
    results["hard_gates"]["consistency"] = check_consistency_bool(proposal, baseline)

    # Scored: Indicator appropriateness
    results["scored_dimensions"]["indicator_appropriateness"] = (
        check_indicator_appropriateness(proposal, baseline)
    )

    # Scored: Budget coherence
    results["scored_dimensions"]["budget_coherence"] = check_budget_coherence(proposal)

    # Scored: Rationale quality
    results["scored_dimensions"]["rationale_quality"] = check_rationale_quality(
        proposal, baseline
    )

    # Scored: Margin quality
    results["scored_dimensions"]["margin_quality"] = check_margin_quality(proposal, baseline)

    # Scored: Direction validity
    results["scored_dimensions"]["direction_validity"] = check_direction_validity(proposal)

    # Overall pass: all hard gates green AND all scored green
    all_hard = all(results["hard_gates"].values())
    all_scored = all(results["scored_dimensions"].values())
    results["pass"] = all_hard and all_scored

    return results


def check_grounding(proposal, baseline):
    """Every numeric target in the proposal must reference a value from the baseline."""
    baseline_values = extract_baseline_values(baseline)

    for slo in proposal.get("slos", []):
        rationale = slo.get("rationale", "")
        # Extract numbers from the rationale
        numbers_in_rationale = set(re.findall(r"[\d]+\.?[\d]*", rationale))
        # The target itself must be justifiable from the baseline
        # At minimum, the rationale must contain at least one baseline number
        has_baseline_ref = False
        for num_str in numbers_in_rationale:
            try:
                num = float(num_str)
                if num in baseline_values or any(
                    abs(num - bv) < 0.01 * max(abs(bv), 1e-10)
                    for bv in baseline_values
                    if bv != 0
                ):
                    has_baseline_ref = True
                    break
            except ValueError:
                continue
        if not has_baseline_ref:
            return False
    return True


def check_consistency(proposal, baseline):
    """No target tighter than observed value without requires_review flag.

    Delegates to the shared consistency module. Returns True if consistent.
    """
    return check_consistency_bool(proposal, baseline)


def check_indicator_appropriateness(proposal, baseline):
    """Every indicator type present in baseline should have at least one SLI."""
    indicators = baseline.get("indicators", {})
    sli_types = {slo["sli_type"] for slo in proposal.get("slos", [])}

    # Latency and availability/error_rate are always expected if present
    if "latency" in indicators and "latency" not in sli_types:
        return False
    if (
        "error_rate" in indicators
        and "availability" not in sli_types
        and "error_rate" not in sli_types
    ):
        return False

    return True


def check_budget_coherence(proposal):
    """Error budget and burn rate windows must be internally consistent."""
    for slo in proposal.get("slos", []):
        budget = slo.get("error_budget_percent", 0)
        if budget <= 0 or budget > 100:
            return False

        policy = slo.get("burn_rate_policy", {})
        windows = policy.get("windows", [])
        if not windows:
            return False

        # Burn rates should be positive
        for w in windows:
            if w.get("burn_rate", 0) <= 0:
                return False

    return True


def check_rationale_quality(proposal, baseline):
    """Each rationale must contain at least one numeric value from the baseline."""
    baseline_values = extract_baseline_values(baseline)

    for slo in proposal.get("slos", []):
        rationale = slo.get("rationale", "")
        numbers = re.findall(r"[\d]+\.?[\d]*", rationale)

        has_number = False
        for n in numbers:
            try:
                val = float(n)
                if val in baseline_values or any(
                    abs(val - bv) < 0.01 * max(abs(bv), 1e-10)
                    for bv in baseline_values
                    if bv != 0
                ):
                    has_number = True
                    break
            except ValueError:
                continue

        if not has_number:
            return False

    return True


def extract_baseline_values(baseline):
    """Extract all numeric values from a baseline artifact."""
    values = set()

    def extract_from_dict(d):
        for v in d.values():
            if isinstance(v, (int, float)):
                values.add(float(v))
            elif isinstance(v, dict):
                extract_from_dict(v)

    extract_from_dict(baseline.get("indicators", {}))
    return values
