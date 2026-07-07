#!/usr/bin/env python3
"""Deterministic deviation computation and rule-based first-pass classification.

Stage one of the drift detector. Computes indicators from live evidence using
the same algorithm as baseline.py, compares each indicator against the baseline
reference, determines tolerance band breaches, and assigns a rule-based
first-pass drift class. Produces a drift-signal artifact.

No LLM involvement. Deterministic and reproducible.
"""

import json
import math
import sys

from baseline import compute_baseline
from schemas.validate import validate
from serialize import serialize


# Default tolerance band multiplier (number of standard deviations)
BAND_MULTIPLIER = 2.0

# Epsilon values for stabilized relative deviation near zero.
# Prevents infinite relative deviations when baseline is at or near zero.
EPSILON = {
    "ratio": 0.001,
    "ms": 1.0,
    "rps": 0.01,
    "default": 0.001,
}


def compute_deviation(live_value, baseline_value, stddev, indicator_type="default"):
    """Compute deviation metrics between live and baseline values.

    Args:
        live_value: The observed live indicator value.
        baseline_value: The historical baseline indicator value.
        stddev: The baseline standard deviation for this indicator.
        indicator_type: One of "ratio", "ms", "rps", or "default".
            Determines the epsilon used for stabilized relative deviation.

    Returns:
        A dict with: abs_deviation, rel_deviation, direction,
        band_upper, band_lower, band_breach, breach_magnitude.
    """
    abs_dev = abs(live_value - baseline_value)

    # Stabilized relative deviation for near-zero baselines
    epsilon = EPSILON.get(indicator_type, EPSILON["default"])
    denominator = max(abs(baseline_value), epsilon)
    rel_dev = (live_value - baseline_value) / denominator

    # Direction
    diff = live_value - baseline_value
    if abs(diff) < epsilon * 0.01:  # effectively zero
        direction = "stable"
    elif diff > 0:
        direction = "increasing"
    else:
        direction = "decreasing"

    # Tolerance bands
    band_upper = baseline_value + BAND_MULTIPLIER * stddev
    band_lower = baseline_value - BAND_MULTIPLIER * stddev

    # Band breach (strict inequality: at the boundary is not a breach)
    band_breach = live_value > band_upper or live_value < band_lower

    # Normalized breach magnitude (for dominant signal ranking)
    band_width = band_upper - band_lower
    if band_width > 0:
        breach_magnitude = abs_dev / (band_width / 2) if band_breach else 0.0
    else:
        breach_magnitude = float("inf") if abs_dev > 0 else 0.0

    return {
        "abs_deviation": abs_dev,
        "rel_deviation": rel_dev,
        "direction": direction,
        "band_upper": band_upper,
        "band_lower": band_lower,
        "band_breach": band_breach,
        "breach_magnitude": breach_magnitude,
    }


def classify_indicator(name, direction, band_breach):
    """Rule-based first-pass classification for a single indicator.

    Args:
        name: The indicator name (e.g. "latency_p99_ms", "error_rate_ratio").
        direction: One of "increasing", "decreasing", "stable".
        band_breach: Whether the tolerance band was breached.

    Returns:
        A string from the drift taxonomy enum.
    """
    if not band_breach:
        return "no_significant_drift"

    # Map indicator name patterns to drift classes
    if "dependency" in name:
        return "dependency_latency_regression" if direction == "increasing" else "no_significant_drift"
    elif "category" in name or "breakdown" in name:
        return "error_category_shift" if band_breach else "no_significant_drift"
    elif "latency" in name:
        return "latency_regression" if direction == "increasing" else "latency_improvement"
    elif "error" in name:
        return "error_rate_elevation" if direction == "increasing" else "error_rate_reduction"
    elif "throughput" in name:
        return "throughput_collapse" if direction == "decreasing" else "throughput_surge"
    elif "cpu" in name or "memory" in name or "saturation" in name:
        return "saturation_approach" if direction == "increasing" else "no_significant_drift"
    elif "availability" in name:
        return "availability_drop" if direction == "decreasing" else "no_significant_drift"

    return "no_significant_drift"


def compute_drift_signal(combined_input):
    """Compute the drift-signal artifact from live evidence + baseline.

    Args:
        combined_input: A dict with keys "live_evidence" (conforming to
            evidence.schema.json) and "baseline" (conforming to
            baseline.schema.json).

    Returns:
        A dict conforming to drift-signal.schema.json.
    """
    live_evidence = combined_input["live_evidence"]
    baseline = combined_input["baseline"]

    # Compute live indicators using the same algorithm as baseline computation
    live_baseline = compute_baseline(live_evidence)

    indicators = []
    breached = []

    # Define indicator mappings: (name, live_accessor, baseline_accessor, stddev_accessor, type)
    indicator_defs = [
        (
            "latency_p99_ms",
            lambda lb: lb["indicators"]["latency"]["p99_ms"],
            lambda b: b["indicators"]["latency"]["p99_ms"],
            lambda b: b["indicators"]["latency"]["stddev_ms"],
            "ms",
        ),
        (
            "latency_p50_ms",
            lambda lb: lb["indicators"]["latency"]["p50_ms"],
            lambda b: b["indicators"]["latency"]["p50_ms"],
            lambda b: b["indicators"]["latency"]["stddev_ms"],
            "ms",
        ),
        (
            "error_rate_ratio",
            lambda lb: lb["indicators"]["error_rate"]["ratio"],
            lambda b: b["indicators"]["error_rate"]["ratio"],
            lambda b: b["indicators"]["error_rate"]["stddev"],
            "ratio",
        ),
        (
            "availability_ratio",
            lambda lb: lb["indicators"]["availability"]["ratio"],
            lambda b: b["indicators"]["availability"]["ratio"],
            lambda b: b["indicators"]["error_rate"]["stddev"],
            "ratio",
        ),
        (
            "throughput_mean_rps",
            lambda lb: lb["indicators"]["throughput"]["mean_rps"],
            lambda b: b["indicators"]["throughput"]["mean_rps"],
            lambda b: b["indicators"]["throughput"]["stddev_rps"],
            "rps",
        ),
    ]

    for name, live_fn, base_fn, stddev_fn, ind_type in indicator_defs:
        try:
            live_val = live_fn(live_baseline)
            base_val = base_fn(baseline)
            stddev_val = stddev_fn(baseline)
        except (KeyError, TypeError):
            indicators.append({
                "name": name,
                "live_value": 0,
                "baseline_value": 0,
                "abs_deviation": 0,
                "rel_deviation": 0,
                "direction": "stable",
                "band_upper": 0,
                "band_lower": 0,
                "band_breach": False,
                "first_pass_class": "no_significant_drift",
                "status": "skipped",
                "skip_reason": "indicator {} not available in live or baseline data".format(name),
            })
            continue

        dev = compute_deviation(live_val, base_val, stddev_val, ind_type)
        drift_class = classify_indicator(name, dev["direction"], dev["band_breach"])

        ind = {
            "name": name,
            "live_value": live_val,
            "baseline_value": base_val,
            "abs_deviation": dev["abs_deviation"],
            "rel_deviation": dev["rel_deviation"],
            "direction": dev["direction"],
            "band_upper": dev["band_upper"],
            "band_lower": dev["band_lower"],
            "band_breach": dev["band_breach"],
            "first_pass_class": drift_class,
        }

        indicators.append(ind)

        if dev["band_breach"]:
            breached.append((name, drift_class, dev["breach_magnitude"]))

    # Add saturation indicators if available in the baseline
    sat_baseline = baseline.get("indicators", {}).get("saturation", {})
    if sat_baseline.get("available", False):
        sat_live = live_baseline.get("indicators", {}).get("saturation", {})
        if sat_live and sat_live.get("available", False):
            for met_name, met_type in [
                ("cpu_mean_ratio", "ratio"),
                ("memory_mean_ratio", "ratio"),
            ]:
                try:
                    live_val = sat_live[met_name]
                    base_val = sat_baseline[met_name]
                    # Use 0.1 as default stddev for saturation if not available
                    stddev_val = 0.1

                    dev = compute_deviation(live_val, base_val, stddev_val, met_type)
                    drift_class = classify_indicator(
                        met_name, dev["direction"], dev["band_breach"]
                    )

                    ind = {
                        "name": met_name,
                        "live_value": live_val,
                        "baseline_value": base_val,
                        "abs_deviation": dev["abs_deviation"],
                        "rel_deviation": dev["rel_deviation"],
                        "direction": dev["direction"],
                        "band_upper": dev["band_upper"],
                        "band_lower": dev["band_lower"],
                        "band_breach": dev["band_breach"],
                        "first_pass_class": drift_class,
                    }

                    indicators.append(ind)
                    if dev["band_breach"]:
                        breached.append((met_name, drift_class, dev["breach_magnitude"]))
                except (KeyError, TypeError):
                    pass
        else:
            # Saturation in baseline but not in live evidence: mark as skipped
            for met_name in ["cpu_mean_ratio", "memory_mean_ratio"]:
                indicators.append({
                    "name": met_name,
                    "live_value": 0,
                    "baseline_value": sat_baseline.get(met_name, 0),
                    "abs_deviation": 0,
                    "rel_deviation": 0,
                    "direction": "stable",
                    "band_upper": 0,
                    "band_lower": 0,
                    "band_breach": False,
                    "first_pass_class": "no_significant_drift",
                    "status": "skipped",
                    "skip_reason": "saturation data not available in live sample",
                })

    # Trace-derived indicators (if both baseline and live have trace data)
    trace_baseline = baseline.get("indicators", {}).get("trace_latency", {})
    if trace_baseline.get("available", False):
        trace_live = live_baseline.get("indicators", {}).get("trace_latency", {})
        if trace_live and trace_live.get("available", False):
            # Top dependency p99 comparison
            live_dep_p99 = trace_live.get("top_dependency_p99_ms", 0)
            base_dep_p99 = trace_baseline.get("top_dependency_p99_ms", 0)
            # Use 20% of baseline as default stddev for trace indicators
            trace_stddev = base_dep_p99 * 0.2 if base_dep_p99 > 0 else 10.0

            dev = compute_deviation(live_dep_p99, base_dep_p99, trace_stddev, "ms")
            drift_class = "dependency_latency_regression" if dev["band_breach"] and dev["direction"] == "increasing" else "no_significant_drift"

            ind = {
                "name": "dependency_p99_ms",
                "live_value": live_dep_p99,
                "baseline_value": base_dep_p99,
                "abs_deviation": dev["abs_deviation"],
                "rel_deviation": dev["rel_deviation"],
                "direction": dev["direction"],
                "band_upper": dev["band_upper"],
                "band_lower": dev["band_lower"],
                "band_breach": dev["band_breach"],
                "first_pass_class": drift_class,
            }
            indicators.append(ind)
            if dev["band_breach"]:
                breached.append(("dependency_p99_ms", drift_class, dev["breach_magnitude"]))

    # Log-derived indicators (if both baseline and live have log data)
    log_baseline = baseline.get("indicators", {}).get("error_breakdown", {})
    if log_baseline.get("available", False):
        log_live = live_baseline.get("indicators", {}).get("error_breakdown", {})
        if log_live and log_live.get("available", False):
            live_ratio = log_live.get("top_category_ratio", 0)
            base_ratio = log_baseline.get("top_category_ratio", 0)
            # Use 10% of baseline ratio as stddev
            log_stddev = base_ratio * 0.1 if base_ratio > 0 else 0.05

            dev = compute_deviation(live_ratio, base_ratio, log_stddev, "ratio")
            drift_class = "error_category_shift" if dev["band_breach"] else "no_significant_drift"

            ind = {
                "name": "error_top_category_ratio",
                "live_value": live_ratio,
                "baseline_value": base_ratio,
                "abs_deviation": dev["abs_deviation"],
                "rel_deviation": dev["rel_deviation"],
                "direction": dev["direction"],
                "band_upper": dev["band_upper"],
                "band_lower": dev["band_lower"],
                "band_breach": dev["band_breach"],
                "first_pass_class": drift_class,
            }
            indicators.append(ind)
            if dev["band_breach"]:
                breached.append(("error_top_category_ratio", drift_class, dev["breach_magnitude"]))

    # Determine dominant signal
    if breached:
        breached.sort(key=lambda x: x[2], reverse=True)
        dominant = {
            "indicator": breached[0][0],
            "class": breached[0][1],
            "breach_magnitude": breached[0][2],
        }
    else:
        dominant = {
            "indicator": "none",
            "class": "no_significant_drift",
            "breach_magnitude": 0.0,
        }

    drift_signal = {
        "schema_version": 1,
        "service": baseline.get("service", live_evidence.get("service", "unknown")),
        "evaluation_window": live_evidence.get("lookback_window", "1h"),
        "evaluated_at": live_evidence.get("collected_at", ""),
        "baseline_schema_version": baseline.get("schema_version", 1),
        "indicators": indicators,
        "dominant_signal": dominant,
        "all_breached_indicators": [b[0] for b in breached],
        "provenance": {
            "prometheus_endpoint": live_evidence.get("provenance", {}).get(
                "prometheus_endpoint", ""
            ),
            "query_timestamps": live_evidence.get("provenance", {}).get(
                "query_timestamps", {"start": "", "end": ""}
            ),
            "coverage_ratio": live_evidence.get("coverage_ratio", 0.0),
        },
    }

    validate(drift_signal, "drift-signal")
    return drift_signal


def main():
    """Read combined input from stdin, write drift-signal to stdout."""
    combined = json.load(sys.stdin)
    signal = compute_drift_signal(combined)
    sys.stdout.write(serialize(signal))


if __name__ == "__main__":
    main()
