"""Shared consistency validation for SLO proposals against baselines.

Handles directionality (lte/gte) for all five SLI types in the four golden
signals framework, plus margin/headroom validation.
"""

# Direction mapping: which target_op is correct for each SLI type
EXPECTED_OPS = {
    "latency": "lte",       # lower is better
    "error_rate": "lte",    # lower is better
    "saturation": "lte",    # lower is better
    "availability": "gte",  # higher is better
    "throughput": "gte",    # higher is better
}

# For "lte" types: "tighter" means the target is LOWER than observed
# For "gte" types: "tighter" means the target is HIGHER than observed
# Headroom goes in the opposite direction of "tighter":
#   lte: headroom = target ABOVE observed (target > observed is loose/safe)
#   gte: headroom = target BELOW observed (target < observed is loose/safe)

# Maximum looseness: reject targets more than this many stddev in the "loose" direction
MAX_LOOSENESS_STDDEV = 5.0

# Maturity tier headroom multipliers (stddev multiplier)
MATURITY_HEADROOM = {
    "new": (2.0, 3.0),      # 2-3 stddev
    "growing": (1.0, 2.0),  # 1-2 stddev
    "mature": (0.5, 1.0),   # 0.5-1 stddev
}


def check_consistency(proposal, baseline):
    """Check that proposal targets are consistent with baseline values.

    Returns a list of error strings (empty if all consistent).
    Checks:
    1. target_op matches expected direction for sli_type
    2. slo_target must be tighter than observed (aspirational)
    3. sla_target must be looser than observed (commitment with headroom)
    4. Neither target may equal observed
    5. sla_target must not be excessively loose (>5 stddev from observed)
    6. slo_target must be between observed and sla_target in ambition
    """
    errors = []
    indicators = baseline.get("indicators", {})

    for slo in proposal.get("slos", []):
        sli_type = slo.get("sli_type", "")
        slo_target = slo.get("slo_target", 0)
        sla_target = slo.get("sla_target", 0)
        target_op = slo.get("target_op", "")
        name = slo.get("sli_name", "unnamed")

        # Check 1: target_op direction
        expected_op = EXPECTED_OPS.get(sli_type)
        if expected_op and target_op != expected_op:
            errors.append(
                f"SLO '{name}': target_op '{target_op}' is wrong for "
                f"sli_type '{sli_type}', expected '{expected_op}'"
            )

        # Get observed value and stddev for this SLI type
        observed, stddev = _get_observed_and_stddev(sli_type, indicators)
        if observed is None:
            continue  # Can't check without observed data

        # Skip checks for boundary values where improvement is impossible
        # e.g., availability = 1.0 (can't go above 100%), error_rate = 0 (can't go below 0)
        op = EXPECTED_OPS.get(sli_type, "lte")
        at_boundary = (op == "gte" and observed >= 1.0) or (op == "lte" and observed <= 0)
        if at_boundary:
            continue

        # Check 2: slo_target must be tighter than observed
        if not _is_tighter(slo_target, observed, sli_type):
            errors.append(
                f"SLO '{name}': slo_target {slo_target} is not tighter than "
                f"observed {observed} for {sli_type} — SLO must be aspirational"
            )

        # Check 3: sla_target must be looser than observed
        if _is_tighter(sla_target, observed, sli_type):
            errors.append(
                f"SLO '{name}': sla_target {sla_target} is tighter than "
                f"observed {observed} for {sli_type} — SLA must have headroom"
            )

        # Check 4: Neither target may equal observed
        if slo_target == observed:
            errors.append(
                f"SLO '{name}': slo_target {slo_target} equals observed value "
                f"{observed} — must include margin"
            )
        if sla_target == observed:
            errors.append(
                f"SLO '{name}': sla_target {sla_target} equals observed value "
                f"{observed} — must include margin/headroom"
            )

        # Check 5: sla_target not excessively loose
        if stddev and stddev > 0:
            looseness = _looseness_in_stddev(sla_target, observed, stddev, sli_type)
            if looseness > MAX_LOOSENESS_STDDEV:
                errors.append(
                    f"SLO '{name}': sla_target {sla_target} is excessively loose "
                    f"({looseness:.1f} stddev from observed {observed})"
                )

        # Check 6: slo_target must be between observed and sla_target
        op = EXPECTED_OPS.get(sli_type, "lte")
        if op == "lte":
            # lower is better: slo_target < observed < sla_target
            if not (slo_target < observed <= sla_target or slo_target <= observed < sla_target):
                if slo_target >= sla_target:
                    errors.append(
                        f"SLO '{name}': slo_target {slo_target} must be less than "
                        f"sla_target {sla_target} for lte metric"
                    )
        else:
            # higher is better: sla_target < observed < slo_target
            if not (sla_target < observed <= slo_target or sla_target <= observed < slo_target):
                if slo_target <= sla_target:
                    errors.append(
                        f"SLO '{name}': slo_target {slo_target} must be greater than "
                        f"sla_target {sla_target} for gte metric"
                    )

    return errors


def check_consistency_bool(proposal, baseline):
    """Boolean version for the eval rubric. Returns True if consistent."""
    return len(check_consistency(proposal, baseline)) == 0


def check_margin_quality(proposal, baseline):
    """Scored dimension: verify both targets include appropriate margin from observed.
    Returns True if all slo_target and sla_target values differ from observed.
    """
    indicators = baseline.get("indicators", {})

    for slo in proposal.get("slos", []):
        sli_type = slo.get("sli_type", "")
        slo_target = slo.get("slo_target", 0)
        sla_target = slo.get("sla_target", 0)

        observed, _ = _get_observed_and_stddev(sli_type, indicators)
        if observed is None:
            continue

        if slo_target == observed:
            return False
        if sla_target == observed:
            return False

    return True


def check_direction_validity(proposal):
    """Scored dimension: verify all target_ops match expected direction.
    Returns True if all SLOs have correct target_op.
    """
    for slo in proposal.get("slos", []):
        sli_type = slo.get("sli_type", "")
        target_op = slo.get("target_op", "")
        expected = EXPECTED_OPS.get(sli_type)
        if expected and target_op != expected:
            return False
    return True


def _get_observed_and_stddev(sli_type, indicators):
    """Extract the observed value and stddev for a given SLI type."""
    if sli_type == "latency":
        lat = indicators.get("latency", {})
        return lat.get("p99_ms"), lat.get("stddev_ms")
    elif sli_type == "error_rate":
        err = indicators.get("error_rate", {})
        return err.get("ratio"), err.get("stddev")
    elif sli_type == "availability":
        avail = indicators.get("availability", {})
        err_stddev = indicators.get("error_rate", {}).get("stddev")
        return avail.get("ratio"), err_stddev
    elif sli_type == "throughput":
        tp = indicators.get("throughput", {})
        return tp.get("mean_rps"), tp.get("stddev_rps")
    elif sli_type == "saturation":
        # Saturation has CPU and memory sub-metrics; the LLM may propose
        # separate SLOs for each. Return None to skip consistency checks
        # since we can't know which sub-metric the SLO refers to.
        return None, None
    return None, None


def _is_tighter(target, observed, sli_type):
    """Check if a target is tighter (more ambitious) than observed.

    For lte types (lower is better): tighter means target < observed
    For gte types (higher is better): tighter means target > observed
    """
    op = EXPECTED_OPS.get(sli_type, "lte")
    if op == "lte":
        return target < observed
    else:
        return target > observed


def _looseness_in_stddev(target, observed, stddev, sli_type):
    """Compute how many stddev the target is from observed in the loose direction.

    For lte types: looseness = (target - observed) / stddev (positive = loose)
    For gte types: looseness = (observed - target) / stddev (positive = loose)
    """
    op = EXPECTED_OPS.get(sli_type, "lte")
    if op == "lte":
        return (target - observed) / stddev
    else:
        return (observed - target) / stddev
