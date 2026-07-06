#!/usr/bin/env python3
"""Deterministic baseline computation from evidence bundle."""

import json
import math
import sys

from schemas.validate import validate
from serialize import serialize


def compute_percentile_from_histogram(buckets, total_count, quantile):
    """Compute a percentile from cumulative histogram buckets using linear interpolation.

    Uses the Prometheus histogram_quantile algorithm.
    Returns value in the same unit as the bucket boundaries.
    """
    rank = quantile * total_count
    prev_count = 0
    prev_bound = 0.0

    for bucket in buckets:
        le = bucket["le"]
        count = bucket["count"]

        # Skip +Inf bucket for interpolation
        if isinstance(le, str) and le == "+Inf":
            continue

        if count >= rank:
            # Interpolate within this bucket
            fraction = (rank - prev_count) / (count - prev_count) if count > prev_count else 0
            return prev_bound + fraction * (le - prev_bound)

        prev_count = count
        prev_bound = le

    # If we get here, use the last finite bucket boundary
    return prev_bound


def compute_stddev_from_histogram(buckets, total_count, hist_sum):
    """Estimate standard deviation from histogram using bucket midpoints.

    For the +Inf bucket, uses 2x the previous bucket boundary as the upper estimate.
    """
    mean = hist_sum / total_count

    prev_bound = 0.0
    prev_count = 0
    variance_sum = 0.0

    for bucket in buckets:
        le = bucket["le"]
        count = bucket["count"]
        bucket_count = count - prev_count

        if isinstance(le, str) and le == "+Inf":
            # Use 2x previous bound as upper estimate
            midpoint = prev_bound * 2 if prev_bound > 0 else 1.0
        else:
            midpoint = (prev_bound + le) / 2

        variance_sum += bucket_count * (midpoint - mean) ** 2

        if not isinstance(le, str):
            prev_bound = le
        prev_count = count

    return math.sqrt(variance_sum / total_count)


def compute_baseline(evidence):
    """Compute a deterministic baseline from an evidence bundle.

    Args:
        evidence: A dict conforming to evidence.schema.json.

    Returns:
        A dict conforming to baseline.schema.json.

    Raises:
        jsonschema.ValidationError: If the evidence is invalid.
        KeyError: If required series data is missing.
    """
    validate(evidence, "evidence")

    series = evidence["series"]
    hist = series["latency_histogram"]
    buckets = hist["buckets"]
    total_count = hist["total_count"]
    hist_sum = hist["sum"]

    # Latency percentiles (convert from seconds to milliseconds)
    p50 = compute_percentile_from_histogram(buckets, total_count, 0.50) * 1000
    p90 = compute_percentile_from_histogram(buckets, total_count, 0.90) * 1000
    p95 = compute_percentile_from_histogram(buckets, total_count, 0.95) * 1000
    p99 = compute_percentile_from_histogram(buckets, total_count, 0.99) * 1000
    stddev = compute_stddev_from_histogram(buckets, total_count, hist_sum) * 1000

    # Error rate
    error_count = int(series["error_total"]["total"])
    request_count = int(series["request_total"]["total"])
    error_ratio = error_count / request_count
    # Binomial approximation for stddev of rate
    error_stddev = math.sqrt(error_ratio * (1 - error_ratio) / request_count)

    # Availability
    availability = 1 - error_ratio

    # Throughput from rate samples
    rate_values = [s["value"] for s in series["request_total"].get("rate_samples", [])]
    if rate_values:
        throughput_mean = sum(rate_values) / len(rate_values)
        sorted_rates = sorted(rate_values)
        p95_idx = math.ceil(0.95 * len(sorted_rates)) - 1
        throughput_p95 = sorted_rates[p95_idx]
        throughput_stddev = math.sqrt(
            sum((v - throughput_mean) ** 2 for v in rate_values) / len(rate_values)
        )
        throughput_count = len(rate_values)
    else:
        throughput_mean = 0.0
        throughput_p95 = 0.0
        throughput_stddev = 0.0
        throughput_count = 0

    # Build baseline
    baseline = {
        "schema_version": 1,
        "service": evidence["service"],
        "namespace": evidence["namespace"],
        "lookback_window": evidence["lookback_window"],
        "generated_at": evidence["collected_at"],
        "indicators": {
            "latency": {
                "p50_ms": p50,
                "p90_ms": p90,
                "p95_ms": p95,
                "p99_ms": p99,
                "stddev_ms": stddev,
                "sample_count": int(total_count),
                "source_query": evidence["provenance"]["queries"].get("latency", ""),
            },
            "error_rate": {
                "ratio": error_ratio,
                "stddev": error_stddev,
                "error_count": error_count,
                "total_count": request_count,
                "source_query": evidence["provenance"]["queries"].get("error_total", ""),
            },
            "availability": {
                "ratio": availability,
                "definition": "1 - (error_count / total_count)",
            },
            "throughput": {
                "mean_rps": throughput_mean,
                "p95_rps": throughput_p95,
                "stddev_rps": throughput_stddev,
                "sample_count": throughput_count,
            },
        },
        "provenance": {
            "prometheus_endpoint": evidence["provenance"]["prometheus_endpoint"],
            "query_timestamps": evidence["provenance"]["query_timestamps"],
            "coverage_ratio": evidence["coverage_ratio"],
        },
    }

    # Add saturation if available
    sat = series.get("saturation", {})
    if sat.get("available", False):
        cpu_samples = sat.get("cpu", {}).get("samples", [])
        mem_samples = sat.get("memory", {}).get("samples", [])

        baseline["indicators"]["saturation"] = {
            "cpu_mean_ratio": sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0.0,
            "cpu_p95_ratio": (
                sorted(cpu_samples)[math.ceil(0.95 * len(cpu_samples)) - 1]
                if cpu_samples
                else 0.0
            ),
            "memory_mean_ratio": (
                sum(mem_samples) / len(mem_samples) if mem_samples else 0.0
            ),
            "memory_p95_ratio": (
                sorted(mem_samples)[math.ceil(0.95 * len(mem_samples)) - 1]
                if mem_samples
                else 0.0
            ),
            "available": True,
        }

    validate(baseline, "baseline")
    return baseline


def main():
    """Read evidence from stdin, write baseline to stdout."""
    evidence = json.load(sys.stdin)
    baseline = compute_baseline(evidence)
    sys.stdout.write(serialize(baseline))


if __name__ == "__main__":
    main()
