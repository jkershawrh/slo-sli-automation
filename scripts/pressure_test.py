#!/usr/bin/env python3
"""sloscope pressure test: ramp concurrency until the breaking point.

Usage:
  python3 scripts/pressure_test.py
  python3 scripts/pressure_test.py --max 200
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Reuse load_test's run_load function
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from load_test import run_load, load_evidence


def main():
    parser = argparse.ArgumentParser(description="sloscope pressure test")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--max", type=int, default=200, help="max concurrency")
    parser.add_argument("--step", type=int, default=10, help="concurrency step")
    parser.add_argument("--threshold", type=float, default=0.05, help="error rate threshold")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "pressure-test-results.json"))
    args = parser.parse_args()

    evidence = load_evidence()
    payload = {"evidence": evidence}

    results = []
    breaking_point = None

    print(f"Pressure test: ramping from {args.step} to {args.max} concurrent")
    print(f"{'Conc':>5} {'Reqs':>6} {'p99':>8} {'RPS':>8} {'Err%':>6} {'Status'}")
    print("-" * 50)

    for conc in range(args.step, args.max + 1, args.step):
        r = asyncio.run(run_load(args.url, "POST", "/api/v1/baseline", payload, conc, 10))
        status = "OK" if r.error_rate < args.threshold else "BREAK"

        print(f"{conc:>5} {r.total_requests:>6} {r.p99_ms:>7.1f}ms {r.rps:>7.1f} {r.error_rate:>5.1%} {status}")

        results.append({
            "concurrency": conc, "requests": r.total_requests,
            "p99_ms": round(r.p99_ms, 1), "rps": round(r.rps, 1),
            "error_rate": round(r.error_rate, 4),
        })

        if r.error_rate >= args.threshold:
            breaking_point = conc
            print(f"\nBREAKING POINT: {conc} concurrent (error_rate={r.error_rate:.1%})")
            break

    if not breaking_point:
        print(f"\nNo breaking point found up to {args.max} concurrent")

    with open(args.output, "w") as f:
        json.dump({"breaking_point": breaking_point, "threshold": args.threshold, "results": results}, f, indent=2)
    print(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
