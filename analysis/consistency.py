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
    2. Target is not tighter than observed without requires_review
    3. Target is not excessively loose (>5 stddev from observed)
    4. Target is not exactly equal to observed (must have margin)
    5. All five SLI types are handled
    """
    errors = []
    indicators = baseline.get("indicators", {})

    for slo in proposal.get("slos", []):
        sli_type = slo.get("sli_type", "")
        target = slo.get("target", 0)
        target_op = slo.get("target_op", "")
        requires_review = slo.get("requires_review", False)
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

        # Check 2: Target not tighter than observed without requires_review
        if _is_tighter(target, observed, sli_type) and not requires_review:
            errors.append(
                f"SLO '{name}': target {target} is tighter than observed "
                f"{observed} for {sli_type} without requires_review flag"
            )

        # Check 3: Target not excessively loose
        if stddev and stddev > 0:
            looseness = _looseness_in_stddev(target, observed, stddev, sli_type)
            if looseness > MAX_LOOSENESS_STDDEV:
                errors.append(
                    f"SLO '{name}': target {target} is excessively loose "
                    f"({looseness:.1f} stddev from observed {observed})"
                )

        # Check 4: Target not exactly equal to observed
        if target == observed:
            errors.append(
                f"SLO '{name}': target {target} equals observed value "
                f"{observed} — must include margin/headroom"
            )

    return errors


def check_consistency_bool(proposal, baseline):
    """Boolean version for the eval rubric. Returns True if consistent."""
    return len(check_consistency(proposal, baseline)) == 0


def check_margin_quality(proposal, baseline):
    """Scored dimension: verify targets include appropriate margin.
    Returns True if all targets have non-zero margin from observed.
    """
    indicators = baseline.get("indicators", {})

    for slo in proposal.get("slos", []):
        sli_type = slo.get("sli_type", "")
        target = slo.get("target", 0)

        observed, _ = _get_observed_and_stddev(sli_type, indicators)
        if observed is None:
            continue

        if target == observed:
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
        sat = indicators.get("saturation", {})
        return sat.get("cpu_p95_ratio"), None  # No stddev available for saturation in schema
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
