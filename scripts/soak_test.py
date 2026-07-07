#!/usr/bin/env python3
"""sloscope soak test: sustained operation monitoring for memory leaks and degradation.

Usage:
  python3 scripts/soak_test.py --duration 120  # 2 hours in minutes
  python3 scripts/soak_test.py --duration 30   # 30 minutes (quick check)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_pipeline_cycle(base_url, evidence, baseline_ref, drift_live):
    """Run one full pipeline cycle and return timing."""
    timings = {}

    start = time.perf_counter()
    r = httpx.post(f"{base_url}/api/v1/baseline", json={"evidence": evidence}, timeout=30)
    timings["baseline_ms"] = (time.perf_counter() - start) * 1000
    timings["baseline_ok"] = r.status_code == 200

    start = time.perf_counter()
    r = httpx.post(f"{base_url}/api/v1/drift/signal",
                    json={"baseline": baseline_ref, "live_evidence": drift_live}, timeout=30)
    timings["drift_ms"] = (time.perf_counter() - start) * 1000
    timings["drift_ok"] = r.status_code == 200

    return timings


def get_server_health(base_url):
    """Check server health and response time."""
    try:
        start = time.perf_counter()
        r = httpx.get(f"{base_url}/health", timeout=5)
        return {
            "healthy": r.status_code == 200,
            "response_ms": (time.perf_counter() - start) * 1000,
        }
    except Exception:
        return {"healthy": False, "response_ms": -1}


def main():
    parser = argparse.ArgumentParser(description="sloscope soak test")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--duration", type=int, default=30, help="duration in minutes")
    parser.add_argument("--interval", type=int, default=30, help="seconds between cycles")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "soak-test-results.json"))
    args = parser.parse_args()

    evidence = json.load(open(PROJECT_ROOT / "testdata" / "evidence_checkout_api.json"))
    baseline_ref = json.load(open(PROJECT_ROOT / "testdata" / "drift_baseline_reference.json"))
    drift_live = json.load(open(PROJECT_ROOT / "testdata" / "drift_live_latency_regression.json"))

    samples = []
    start_time = time.time()
    end_time = start_time + args.duration * 60
    cycle = 0

    print(f"Soak test: {args.duration} min, {args.interval}s intervals")
    print(f"{'Cycle':>5} {'Elapsed':>8} {'Health':>8} {'Base_ms':>8} {'Drift_ms':>8} {'Status'}")
    print("-" * 55)

    while time.time() < end_time:
        cycle += 1
        elapsed_min = (time.time() - start_time) / 60

        health = get_server_health(args.url)
        timings = run_pipeline_cycle(args.url, evidence, baseline_ref, drift_live)

        sample = {
            "cycle": cycle,
            "elapsed_min": round(elapsed_min, 1),
            **health,
            **timings,
        }
        samples.append(sample)

        status = "OK" if health["healthy"] and timings["baseline_ok"] and timings["drift_ok"] else "FAIL"
        print(f"{cycle:>5} {elapsed_min:>7.1f}m {health['response_ms']:>7.1f}ms {timings['baseline_ms']:>7.1f}ms {timings['drift_ms']:>7.1f}ms {status}")

        if len(samples) > 10:
            first_baseline = samples[0]["baseline_ms"]
            curr_baseline = timings["baseline_ms"]
            if curr_baseline > first_baseline * 3:
                print(f"WARNING: baseline latency tripled ({first_baseline:.0f}ms -> {curr_baseline:.0f}ms)")

        time.sleep(args.interval)

    # Summary
    baseline_times = [s["baseline_ms"] for s in samples if s.get("baseline_ok")]
    drift_times = [s["drift_ms"] for s in samples if s.get("drift_ok")]
    failures = sum(1 for s in samples if not s.get("healthy") or not s.get("baseline_ok"))

    summary = {
        "duration_min": args.duration,
        "cycles": len(samples),
        "failures": failures,
        "baseline_avg_ms": round(sum(baseline_times) / len(baseline_times), 1) if baseline_times else 0,
        "drift_avg_ms": round(sum(drift_times) / len(drift_times), 1) if drift_times else 0,
        "baseline_p99_ms": round(sorted(baseline_times)[int(0.99 * len(baseline_times))] if baseline_times else 0, 1),
    }

    print(f"\n=== Soak Summary ===")
    print(f"Duration: {args.duration} min, {len(samples)} cycles, {failures} failures")
    print(f"Baseline: avg={summary['baseline_avg_ms']}ms, p99={summary['baseline_p99_ms']}ms")
    print(f"Drift: avg={summary['drift_avg_ms']}ms")

    with open(args.output, "w") as f:
        json.dump({"summary": summary, "samples": samples}, f, indent=2)
    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
