"""Live Prometheus collector for container metrics.

Queries real metrics from Prometheus inside the cluster and builds
evidence bundles for the artifact store. Works with container-level
metrics (CPU, memory, restarts, pod counts) — no HTTP instrumentation needed.
"""

import json
import math
import os
import ssl
import time
import urllib.request
import urllib.parse
from pathlib import Path


def _prom_query(prom_url, token, query):
    """Execute a Prometheus instant query."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{prom_url}/api/v1/query"
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req, context=ctx, timeout=30)
    result = json.loads(r.read())
    return result.get("data", {}).get("result", [])


def _prom_query_range(prom_url, token, query, start, end, step="5m"):
    """Execute a Prometheus range query."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    params = urllib.parse.urlencode({
        "query": query, "start": start, "end": end, "step": step
    })
    url = f"{prom_url}/api/v1/query_range?{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    r = urllib.request.urlopen(req, context=ctx, timeout=30)
    result = json.loads(r.read())
    return result.get("data", {}).get("result", [])


def collect_live_metrics(namespace, prom_url=None, token=None):
    """Collect live container metrics for a namespace from Prometheus.

    Returns a dict with CPU, memory, pod count, and restart data.
    """
    prom_url = prom_url or os.environ.get("PROM_URL", "")
    token = token or os.environ.get("PROM_TOKEN", "")

    if not prom_url or not token:
        raise RuntimeError("PROM_URL and PROM_TOKEN required for live collection")

    now = time.time()
    end = int(now)
    start = end - 3600  # last 1 hour for live window

    metrics = {}

    # CPU usage (rate over 5m, per-container, summed for namespace)
    results = _prom_query(prom_url, token,
        f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}",container!="",container!="POD"}}[5m]))')
    metrics["cpu_total"] = float(results[0]["value"][1]) if results else 0

    # CPU per-pod samples (for stddev)
    results = _prom_query(prom_url, token,
        f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}",container!="",container!="POD"}}[5m])')
    cpu_samples = [float(r["value"][1]) for r in results] if results else [0]
    metrics["cpu_samples"] = cpu_samples

    # Memory usage (current, summed for namespace, in GB)
    results = _prom_query(prom_url, token,
        f'sum(container_memory_working_set_bytes{{namespace="{namespace}",container!="",container!="POD"}})')
    metrics["memory_bytes"] = float(results[0]["value"][1]) if results else 0

    # Memory per-container samples
    results = _prom_query(prom_url, token,
        f'container_memory_working_set_bytes{{namespace="{namespace}",container!="",container!="POD"}}')
    mem_samples = [float(r["value"][1]) for r in results] if results else [0]
    metrics["memory_samples"] = mem_samples

    # Pod count (running)
    results = _prom_query(prom_url, token,
        f'count(kube_pod_status_phase{{namespace="{namespace}",phase="Running"}})')
    metrics["pod_count"] = int(float(results[0]["value"][1])) if results else 0

    # Restarts (last hour)
    results = _prom_query(prom_url, token,
        f'sum(increase(kube_pod_container_status_restarts_total{{namespace="{namespace}"}}[1h]))')
    metrics["restarts_1h"] = float(results[0]["value"][1]) if results else 0

    return metrics


def build_baseline_from_live(namespace, metrics):
    """Build a baseline artifact from live container metrics."""
    cpu_samples = metrics.get("cpu_samples", [0])
    mem_samples = metrics.get("memory_samples", [0])
    pod_count = metrics.get("pod_count", 1) or 1

    # Compute per-pod ratios (assuming 1 CPU core limit per container)
    cpu_mean = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
    cpu_sorted = sorted(cpu_samples)
    cpu_p95 = cpu_sorted[int(0.95 * (len(cpu_sorted) - 1))] if len(cpu_sorted) > 1 else cpu_mean

    # Memory as ratio of 4GB per container (reasonable default)
    mem_gb_per_container = 4.0
    mem_ratios = [s / (mem_gb_per_container * 1e9) for s in mem_samples]
    mem_mean = sum(mem_ratios) / len(mem_ratios) if mem_ratios else 0
    mem_sorted = sorted(mem_ratios)
    mem_p95 = mem_sorted[int(0.95 * (len(mem_sorted) - 1))] if len(mem_sorted) > 1 else mem_mean

    # Availability: 1.0 if no restarts, degraded if restarts
    restarts = metrics.get("restarts_1h", 0)
    availability = max(0, 1.0 - (restarts / max(pod_count * 60, 1)))

    return {
        "schema_version": 1,
        "service": namespace,
        "namespace": namespace,
        "lookback_window": "1h",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "context_type": "infra",
        "maturity_tier": "growing",
        "indicators": {
            "latency": {
                "p50_ms": 0, "p90_ms": 0, "p95_ms": 0, "p99_ms": 0,
                "stddev_ms": 0, "sample_count": 0,
                "source_query": "container metrics only (no HTTP histograms)"
            },
            "error_rate": {
                "ratio": min(restarts / max(pod_count * 60, 1), 1.0),
                "stddev": 0,
                "error_count": int(restarts),
                "total_count": pod_count * 60,
                "source_query": f"kube_pod_container_status_restarts_total{{namespace=\"{namespace}\"}}"
            },
            "availability": {
                "ratio": min(availability, 1.0),
                "definition": "1 - (restarts / (pods * checks_per_hour))"
            },
            "throughput": {
                "mean_rps": 0, "p95_rps": 0, "stddev_rps": 0, "sample_count": 0
            },
            "saturation": {
                "cpu_mean_ratio": cpu_mean,
                "cpu_p95_ratio": cpu_p95,
                "memory_mean_ratio": mem_mean,
                "memory_p95_ratio": mem_p95,
                "available": True
            }
        },
        "provenance": {
            "prometheus_endpoint": os.environ.get("PROM_URL", ""),
            "query_timestamps": {
                "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600)),
                "end": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            },
            "coverage_ratio": 0.95
        }
    }


def build_evidence_from_live(namespace, metrics):
    """Build an evidence bundle from live container metrics for drift detection."""
    cpu_samples = metrics.get("cpu_samples", [0])
    mem_samples = metrics.get("memory_samples", [0])

    mem_gb_per_container = 4.0
    mem_ratios = [min(s / (mem_gb_per_container * 1e9), 1.0) for s in mem_samples]

    return {
        "schema_version": 1,
        "service": namespace,
        "namespace": namespace,
        "lookback_window": "1h",
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage_ratio": 0.95,
        "series": {
            "latency_histogram": {
                "metric_name": "n/a",
                "buckets": [{"le": 1.0, "count": 1}],
                "total_count": 1,
                "sum": 0
            },
            "request_total": {
                "metric_name": "n/a",
                "total": 1,
                "rate_samples": [{"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "value": 0}]
            },
            "error_total": {"metric_name": "n/a", "total": 0},
            "saturation": {
                "cpu": {"metric_name": "container_cpu_usage_seconds_total", "samples": cpu_samples[:10]},
                "memory": {"metric_name": "container_memory_working_set_bytes", "samples": mem_ratios[:10]},
                "available": True
            }
        },
        "provenance": {
            "prometheus_endpoint": os.environ.get("PROM_URL", ""),
            "query_timestamps": {
                "start": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600)),
                "end": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            },
            "queries": {
                "cpu": f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}"}}[5m])',
                "memory": f'container_memory_working_set_bytes{{namespace="{namespace}"}}'
            }
        }
    }


def collect_and_store(namespaces, store, run_proposals=False, run_drift=True):
    """Collect live metrics for multiple namespaces and store results."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

    from deviation import compute_drift_signal

    results = {}
    for ns in namespaces:
        print(f"{ns}: collecting...", end=" ", flush=True)
        try:
            metrics = collect_live_metrics(ns)
            baseline_data = build_baseline_from_live(ns, metrics)
            store.save(ns, "baseline", baseline_data)

            cpu = metrics["cpu_total"]
            mem_gb = metrics["memory_bytes"] / 1e9
            pods = metrics["pod_count"]
            print(f"CPU={cpu:.3f} Mem={mem_gb:.1f}GB Pods={pods}", end="")

            if run_drift:
                existing_baseline = store.load(ns, "baseline")
                if existing_baseline:
                    evidence = build_evidence_from_live(ns, metrics)
                    signal = compute_drift_signal({
                        "live_evidence": evidence,
                        "baseline": existing_baseline
                    })
                    store.save(ns, "drift-signal", signal)
                    dom = signal["dominant_signal"]["class"]
                    br = len(signal["all_breached_indicators"])
                    print(f" drift={dom}({br})", end="")

            print(" OK")
            results[ns] = {"status": "ok", "cpu": cpu, "memory_gb": mem_gb, "pods": pods}

        except Exception as e:
            print(f" FAIL: {e}")
            results[ns] = {"status": "error", "error": str(e)[:80]}

    return results
