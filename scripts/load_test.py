#!/usr/bin/env python3
"""sloscope load test: measure API throughput under concurrent load.

Usage:
  python3 scripts/load_test.py                    # default: localhost:8080
  python3 scripts/load_test.py --url http://host:port
  python3 scripts/load_test.py --endpoint baseline --concurrency 50
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent

@dataclass
class LoadResult:
    endpoint: str
    concurrency: int
    duration_s: float
    total_requests: int
    successful: int
    failed: int
    latencies_ms: list = field(default_factory=list)

    @property
    def p50_ms(self): return self._percentile(0.50)
    @property
    def p95_ms(self): return self._percentile(0.95)
    @property
    def p99_ms(self): return self._percentile(0.99)
    @property
    def rps(self): return self.total_requests / self.duration_s if self.duration_s > 0 else 0
    @property
    def error_rate(self): return self.failed / self.total_requests if self.total_requests > 0 else 0

    def _percentile(self, q):
        if not self.latencies_ms: return 0
        s = sorted(self.latencies_ms)
        idx = int(q * (len(s) - 1))
        return s[idx]


async def run_load(base_url, method, path, payload, concurrency, duration_s):
    """Hit an endpoint with N concurrent workers for M seconds."""
    result = LoadResult(endpoint=path, concurrency=concurrency, duration_s=duration_s,
                         total_requests=0, successful=0, failed=0)
    stop = asyncio.Event()

    async def worker(client):
        while not stop.is_set():
            start = time.perf_counter()
            try:
                if method == "GET":
                    r = await client.get(f"{base_url}{path}")
                else:
                    r = await client.post(f"{base_url}{path}", json=payload)
                elapsed = (time.perf_counter() - start) * 1000
                result.total_requests += 1
                if r.status_code < 400:
                    result.successful += 1
                    result.latencies_ms.append(elapsed)
                else:
                    result.failed += 1
            except Exception:
                result.total_requests += 1
                result.failed += 1

    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [asyncio.create_task(worker(client)) for _ in range(concurrency)]
        await asyncio.sleep(duration_s)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    return result


def load_evidence():
    with open(PROJECT_ROOT / "testdata" / "evidence_checkout_api.json") as f:
        return json.load(f)


def load_baseline():
    sys.path.insert(0, str(PROJECT_ROOT / "analysis"))
    from baseline import compute_baseline
    return compute_baseline(load_evidence())


def main():
    parser = argparse.ArgumentParser(description="sloscope load test")
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--endpoint", default="all", help="all, baseline, drift, propose")
    parser.add_argument("--concurrency", type=int, default=0, help="specific concurrency (0=sweep)")
    parser.add_argument("--duration", type=int, default=15, help="seconds per concurrency level")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "load-test-results.json"))
    args = parser.parse_args()

    evidence = load_evidence()
    baseline = load_baseline()
    drift_baseline = json.load(open(PROJECT_ROOT / "testdata" / "drift_baseline_reference.json"))
    drift_live = json.load(open(PROJECT_ROOT / "testdata" / "drift_live_latency_regression.json"))

    endpoints = {
        "health": ("GET", "/health", None),
        "baseline": ("POST", "/api/v1/baseline", {"evidence": evidence}),
        "drift": ("POST", "/api/v1/drift/signal", {"baseline": drift_baseline, "live_evidence": drift_live}),
    }

    if args.endpoint != "all":
        endpoints = {args.endpoint: endpoints[args.endpoint]}

    concurrency_levels = [args.concurrency] if args.concurrency > 0 else [1, 5, 10, 25, 50, 100]

    results = {}
    print(f"{'Endpoint':<12} {'Conc':>5} {'Reqs':>6} {'p50':>8} {'p95':>8} {'p99':>8} {'RPS':>8} {'Err%':>6}")
    print("-" * 70)

    for name, (method, path, payload) in endpoints.items():
        results[name] = []
        for conc in concurrency_levels:
            r = asyncio.run(run_load(args.url, method, path, payload, conc, args.duration))
            print(f"{name:<12} {conc:>5} {r.total_requests:>6} {r.p50_ms:>7.1f}ms {r.p95_ms:>7.1f}ms {r.p99_ms:>7.1f}ms {r.rps:>7.1f} {r.error_rate:>5.1%}")
            results[name].append({
                "concurrency": conc, "requests": r.total_requests,
                "p50_ms": round(r.p50_ms, 1), "p95_ms": round(r.p95_ms, 1), "p99_ms": round(r.p99_ms, 1),
                "rps": round(r.rps, 1), "error_rate": round(r.error_rate, 4),
            })

    with open(args.output, "w") as f:
        json.dump({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "results": results}, f, indent=2)
    print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
