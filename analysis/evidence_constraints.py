"""Runtime evidence boundaries shared by CLI, HTTP and optional MCP callers.

Structured measurements are authoritative. Model prose is advisory and must not
be treated as independently verified causal or outcome evidence.
"""
import hashlib
import json
import math

from schemas.validate import validate

MIN_COVERAGE = 0.8


class EvidenceConstraintError(ValueError):
    """Abstain rather than turn incomplete or conflicting evidence into a verdict."""


def finite_artifact(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceConstraintError("Non-finite numeric evidence is not admissible")
    if isinstance(value, dict):
        for item in value.values():
            finite_artifact(item)
    elif isinstance(value, list):
        for item in value:
            finite_artifact(item)


def input_digest(artifact):
    finite_artifact(artifact)
    return hashlib.sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require_coverage(artifact):
    finite_artifact(artifact)
    if artifact.get("provenance", {}).get("coverage_ratio", 0) < MIN_COVERAGE:
        raise EvidenceConstraintError("At least 0.8 measured coverage is required; collect more evidence")


def classification_constraints(signal):
    validate(signal, "drift-signal")
    require_coverage(signal)
    measured = [i for i in signal["indicators"] if i.get("status", "measured") == "measured"]
    if not measured:
        raise EvidenceConstraintError("No measured indicators; classification abstained")
    names = [i["name"] for i in measured]
    if len(names) != len(set(names)):
        raise EvidenceConstraintError("Duplicate indicator identities")
    breached = {i["name"] for i in measured if i["band_breach"]}
    if breached != set(signal["all_breached_indicators"]):
        raise EvidenceConstraintError("Breached indicator list conflicts with measured evidence")
    for i in measured:
        from deviation import EPSILON, classify_indicator
        units = {"latency_p99_ms": "ms", "latency_p50_ms": "ms", "dependency_p99_ms": "ms",
                 "error_rate_ratio": "ratio", "availability_ratio": "ratio", "error_top_category_ratio": "ratio",
                 "throughput_mean_rps": "rps", "cpu_mean_ratio": "ratio", "memory_mean_ratio": "ratio"}
        if i["name"] not in units:
            raise EvidenceConstraintError("Unknown indicator identity")
        epsilon = EPSILON[units[i["name"]]]
        diff = i["live_value"] - i["baseline_value"]
        direction = "stable" if abs(diff) < epsilon * 0.01 else ("increasing" if diff > 0 else "decreasing")
        if i["direction"] != direction:
            raise EvidenceConstraintError("Indicator direction conflicts with measured values")
        if i["first_pass_class"] != classify_indicator(i["name"], direction, i["band_breach"]):
            raise EvidenceConstraintError("Indicator class conflicts with measured evidence")
        if i["band_lower"] > i["band_upper"]:
            raise EvidenceConstraintError("Invalid indicator tolerance band")
        outside = i["live_value"] < i["band_lower"] or i["live_value"] > i["band_upper"]
        if outside != i["band_breach"]:
            raise EvidenceConstraintError("Breach flag conflicts with measured tolerance band")
        if not math.isclose(i["abs_deviation"], abs(i["live_value"] - i["baseline_value"]), rel_tol=0.002, abs_tol=1e-6):
            raise EvidenceConstraintError("Deviation conflicts with measured values")
    dominant = signal["dominant_signal"]
    if breached and dominant["indicator"] not in breached:
        raise EvidenceConstraintError("Dominant indicator is not a measured breach")
    if not breached and dominant["class"] != "no_significant_drift":
        raise EvidenceConstraintError("Drift classification has no measured breach")
    if breached:
        observed_class = next(i["first_pass_class"] for i in measured if i["name"] == dominant["indicator"])
        if dominant["class"] != observed_class:
            raise EvidenceConstraintError("Dominant class conflicts with its measured indicator")
    if breached and dominant["class"] == "no_significant_drift":
        raise EvidenceConstraintError("Measured breaches cannot be classified as no drift")
    return {
        "policy": "measured-drift-v1", "input_sha256": input_digest(signal),
        "coverage_ratio": signal["provenance"]["coverage_ratio"],
        "measured_indicators": names, "breached_indicators": sorted(breached),
        "prose_status": "advisory_not_verified_causality",
    }


def proposal_constraints(proposal, baseline):
    """Bind structured targets to identified observations before accepting prose."""
    from consistency import _get_observed_and_stddev
    finite_artifact(proposal)
    require_coverage(baseline)
    errors = []
    if proposal.get("service") != baseline.get("service"):
        errors.append("Proposal service does not match baseline")
    if proposal.get("baseline_schema_version") != baseline.get("schema_version"):
        errors.append("Proposal references a different baseline schema")
    for slo in proposal.get("slos", []):
        kind = slo.get("sli_type")
        if not 0 < slo.get("error_budget_percent", 0) < 100:
            errors.append("Error budget must be strictly between zero and 100 percent")
        observed, _ = _get_observed_and_stddev(kind, baseline["indicators"])
        if kind == "saturation":
            metric = slo.get("evidence_metric")
            sat = baseline["indicators"].get("saturation", {})
            if metric not in ("cpu_mean_ratio", "memory_mean_ratio") or not sat.get("available"):
                errors.append("Saturation requires an available evidence_metric (CPU or memory)")
                continue
            observed = sat.get(metric)
        if observed is None:
            errors.append("No measured observation for proposed indicator")
            continue
        headroom = slo.get("headroom", {})
        if not math.isclose(headroom.get("observed_value", -1), observed, rel_tol=1e-6, abs_tol=1e-8):
            errors.append("Headroom observed_value does not match measured evidence")
        for field in ("slo_target", "sla_target"):
            value = slo.get(field, -1)
            if value < 0 or (kind in ("availability", "error_rate", "saturation") and value > 1):
                errors.append("Target is outside its measured unit bounds")
        if kind == "latency":
            boundaries = baseline["indicators"].get("latency", {}).get("histogram_buckets_seconds")
            if boundaries is not None and slo["sla_target"] / 1000 not in boundaries:
                errors.append("Latency SLA threshold must match an observed histogram bucket")
        if kind == "saturation" and not (slo["slo_target"] < observed < slo["sla_target"]):
            errors.append("Saturation targets require measured headroom and correct direction")
    return errors


def numeric_claim_errors(texts, values):
    """Check numeric citations, including percentages and multipliers.

    This is a numeric boundary, not proof that free-form causal reasoning is true.
    Human review is still required for rationale, remediation and proposed targets.
    """
    import re
    allowed = {float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)}
    errors = []
    for text in texts:
        text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
        for match in re.finditer(r"(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text):
            # Durations are proposed review intervals, not telemetry citations.
            tail = text[match.end():]
            if re.match(r"(?:h|d|m)(?![a-zA-Z])", tail):
                continue
            value = float(match.group())
            if not any(math.isclose(value, n, rel_tol=0.02, abs_tol=1e-8) for n in allowed):
                errors.append("Numeric citation {} is not supported by the evidence or declared policy".format(match.group()))
    return errors


def proposal_claim_errors(proposal, baseline):
    values = {0.0, 0.5, 1.0, 2.0, 3.0}  # Explicit maturity headroom policy constants, not observations.
    def gather(item):
        if isinstance(item, dict):
            for value in item.values(): gather(value)
        elif isinstance(item, list):
            for value in item: gather(value)
        elif isinstance(item, (int, float)) and not isinstance(item, bool): values.add(float(item))
    gather(baseline['indicators'])
    for slo in proposal['slos']:
        gather({k:slo.get(k) for k in ('slo_target','sla_target','error_budget_percent','burn_rate_policy')})
    # Common explicitly calculable ratios used to explain headroom and percentile spread.
    ind=baseline['indicators'];lat=ind.get('latency',{});p99=lat.get('p99_ms',0);p50=lat.get('p50_ms',0);std=lat.get('stddev_ms',0)
    if p99: values.add(100*std/p99)
    if p50: values.add(p99/p50)
    err=ind.get("error_rate",{})
    if err.get("ratio"): values.add(100*err.get("stddev",0)/err["ratio"])
    values.update(v*100 for v in list(values) if 0 <= v <= 1)
    texts=[]
    for slo in proposal['slos']:
        texts.extend([slo.get('rationale',''),slo.get('headroom',{}).get('margin_rationale','')])
    return numeric_claim_errors(texts,values)
