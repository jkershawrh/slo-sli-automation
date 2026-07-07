#!/usr/bin/env python3
"""sloscope benchmark suite.

Measures deterministic computation throughput, LLM proposal/drift quality,
and end-to-end pipeline timing. Outputs benchmark-results.json.

Usage:
  python3 scripts/benchmark.py                    # Local benchmarks only (no LLM)
  python3 scripts/benchmark.py --live             # Include live LLM tests
  python3 scripts/benchmark.py --live --models qwen3-235b,granite-3-2-8b-instruct
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "analysis"))

from baseline import compute_baseline
from deviation import compute_drift_signal
from schemas.validate import validate, is_valid
from consistency import check_consistency, EXPECTED_OPS
from serialize import serialize


def benchmark_baseline_computation():
    """Time deterministic baseline computation across fixtures."""
    results = {}

    fixtures = {
        "metrics_only": PROJECT_ROOT / "testdata" / "evidence_checkout_api.json",
        "full_evidence": PROJECT_ROOT / "testdata" / "evidence_checkout_api_full.json",
    }

    for name, path in fixtures.items():
        if not path.exists():
            results[name] = {"status": "skip", "reason": "fixture not found"}
            continue

        with open(path) as f:
            evidence = json.load(f)

        # Warm up
        compute_baseline(evidence)

        # Measure (10 runs)
        times = []
        for _ in range(10):
            start = time.perf_counter()
            bl = compute_baseline(evidence)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        # Verify determinism
        bl1 = serialize(compute_baseline(evidence))
        bl2 = serialize(compute_baseline(evidence))
        deterministic = bl1 == bl2

        results[name] = {
            "mean_ms": round(sum(times) / len(times), 2),
            "min_ms": round(min(times), 2),
            "max_ms": round(max(times), 2),
            "runs": len(times),
            "deterministic": deterministic,
            "indicators": list(bl["indicators"].keys()),
        }

    return results


def benchmark_deviation_computation():
    """Time deterministic deviation computation."""
    results = {}

    baseline_path = PROJECT_ROOT / "testdata" / "drift_baseline_reference.json"
    if not baseline_path.exists():
        return {"status": "skip"}

    with open(baseline_path) as f:
        baseline_ref = json.load(f)

    drift_fixtures = {
        "latency_regression": PROJECT_ROOT / "testdata" / "drift_live_latency_regression.json",
        "no_drift": PROJECT_ROOT / "testdata" / "drift_live_no_drift.json",
    }

    for name, path in drift_fixtures.items():
        if not path.exists():
            results[name] = {"status": "skip"}
            continue

        with open(path) as f:
            live = json.load(f)

        combined = {"live_evidence": live, "baseline": baseline_ref}

        # Warm up
        compute_drift_signal(combined)

        # Measure (10 runs)
        times = []
        for _ in range(10):
            start = time.perf_counter()
            signal = compute_drift_signal(combined)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        results[name] = {
            "mean_ms": round(sum(times) / len(times), 2),
            "min_ms": round(min(times), 2),
            "max_ms": round(max(times), 2),
            "runs": len(times),
            "dominant_class": signal["dominant_signal"]["class"],
            "indicators_count": len(signal["indicators"]),
            "breached_count": len(signal["all_breached_indicators"]),
        }

    return results


def benchmark_eval_grid():
    """Run the eval grids (proposal + drift) against recorded responses."""
    results = {}

    # Proposal eval
    sys.path.insert(0, str(PROJECT_ROOT / "analysis" / "evals"))
    try:
        from runner import run_eval_suite
        start = time.perf_counter()
        grid = run_eval_suite()
        elapsed = (time.perf_counter() - start) * 1000

        total = len(grid)
        passed = sum(1 for r in grid.values() if r.get("pass"))

        results["proposal_eval"] = {
            "total_scenarios": total,
            "passed": passed,
            "failed": total - passed,
            "eval_time_ms": round(elapsed, 2),
            "scenarios": {name: {"pass": r.get("pass", False)} for name, r in grid.items()},
        }
    except Exception as e:
        results["proposal_eval"] = {"status": "error", "error": str(e)[:100]}

    # Drift eval
    try:
        from drift_runner import run_drift_eval_suite
        start = time.perf_counter()
        grid = run_drift_eval_suite()
        elapsed = (time.perf_counter() - start) * 1000

        total = len(grid)
        passed = sum(1 for r in grid.values() if r.get("pass"))

        results["drift_eval"] = {
            "total_scenarios": total,
            "passed": passed,
            "failed": total - passed,
            "eval_time_ms": round(elapsed, 2),
            "scenarios": {name: {"pass": r.get("pass", False)} for name, r in sorted(grid.items())},
        }
    except Exception as e:
        results["drift_eval"] = {"status": "error", "error": str(e)[:100]}

    return results


def benchmark_e2e_pipeline():
    """Time end-to-end CLI pipeline execution."""
    results = {}
    binary = PROJECT_ROOT / "bin" / "sloscope"

    if not binary.exists():
        return {"status": "skip", "reason": "binary not built"}

    import tempfile

    # Generate dry-run
    with tempfile.TemporaryDirectory() as tmpdir:
        start = time.perf_counter()
        proc = subprocess.run(
            [str(binary), "generate",
             "--service", "checkout-api",
             "--namespace", "payments",
             "--evidence", str(PROJECT_ROOT / "testdata" / "evidence_checkout_api.json"),
             "--out", tmpdir,
             "--dry-run"],
            capture_output=True, text=True, timeout=60
        )
        elapsed = (time.perf_counter() - start) * 1000
        results["generate_dry_run_ms"] = round(elapsed, 2)
        results["generate_dry_run_exit"] = proc.returncode

    # Drift dry-run
    with tempfile.TemporaryDirectory() as tmpdir:
        start = time.perf_counter()
        proc = subprocess.run(
            [str(binary), "drift",
             "--service", "checkout-api",
             "--baseline", str(PROJECT_ROOT / "testdata" / "drift_baseline_reference.json"),
             "--evidence", str(PROJECT_ROOT / "testdata" / "drift_live_latency_regression.json"),
             "--out", tmpdir,
             "--dry-run"],
            capture_output=True, text=True, timeout=60
        )
        elapsed = (time.perf_counter() - start) * 1000
        results["drift_dry_run_ms"] = round(elapsed, 2)
        results["drift_dry_run_exit"] = proc.returncode

    return results


def benchmark_llm_proposal(models, api_keys, base_url):
    """A/B test LLM proposal across models."""
    from propose import propose, SYSTEM_PROMPT

    # Load baseline
    with open(PROJECT_ROOT / "testdata" / "evidence_checkout_api.json") as f:
        evidence = json.load(f)
    baseline = compute_baseline(evidence)

    results = {}

    for model, key in zip(models, api_keys):
        os.environ["LLM_BASE_URL"] = base_url
        os.environ["LLM_API_KEY"] = key
        os.environ["LLM_MODEL"] = model
        os.environ["SLOSCOPE_MATURITY_TIER"] = "growing"
        os.environ["SLOSCOPE_CONTEXT_TYPE"] = "service"

        model_result = {"attempts": []}

        for attempt in range(2):  # 2 attempts per model
            start = time.perf_counter()
            try:
                proposal = propose(baseline)
                elapsed = time.perf_counter() - start

                # Validate
                schema_valid = is_valid(proposal, "proposal")
                consistency_errors = check_consistency(proposal, baseline)

                # Check directions
                direction_correct = True
                for slo in proposal.get("slos", []):
                    expected = EXPECTED_OPS.get(slo.get("sli_type"))
                    if expected and slo.get("target_op") != expected:
                        direction_correct = False

                attempt_result = {
                    "status": "pass" if schema_valid and not consistency_errors and direction_correct else "fail",
                    "latency_s": round(elapsed, 2),
                    "schema_valid": schema_valid,
                    "consistency_errors": len(consistency_errors),
                    "direction_correct": direction_correct,
                    "slos_count": len(proposal.get("slos", [])),
                    "schema_version": proposal.get("schema_version"),
                    "has_slo_target": all("slo_target" in s for s in proposal.get("slos", [])),
                    "has_sla_target": all("sla_target" in s for s in proposal.get("slos", [])),
                }

                if consistency_errors:
                    attempt_result["first_error"] = consistency_errors[0][:80]

                # Extract targets for the report
                attempt_result["targets"] = [{
                    "name": s.get("sli_name"),
                    "type": s.get("sli_type"),
                    "op": s.get("target_op"),
                    "slo": s.get("slo_target"),
                    "sla": s.get("sla_target"),
                } for s in proposal.get("slos", [])]

            except Exception as e:
                elapsed = time.perf_counter() - start
                attempt_result = {
                    "status": "error",
                    "latency_s": round(elapsed, 2),
                    "error": str(e)[:120],
                }

            model_result["attempts"].append(attempt_result)

        # Summary
        passes = sum(1 for a in model_result["attempts"] if a["status"] == "pass")
        model_result["pass_rate"] = passes / len(model_result["attempts"])
        model_result["avg_latency_s"] = round(
            sum(a["latency_s"] for a in model_result["attempts"]) / len(model_result["attempts"]), 2
        )

        results[model] = model_result

    return results


def benchmark_llm_drift(models, api_keys, base_url):
    """Test LLM drift classification across models."""
    from classify import classify

    # Load a drift fixture
    drift_fixture_path = PROJECT_ROOT / "analysis" / "evals" / "fixtures" / "drift" / "latency_regression.json"
    ground_truth_path = PROJECT_ROOT / "analysis" / "evals" / "fixtures" / "drift" / "ground_truth.json"

    if not drift_fixture_path.exists():
        return {"status": "skip"}

    with open(drift_fixture_path) as f:
        drift_signal = json.load(f)
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    expected_class = ground_truth.get("latency_regression", {}).get("class", "latency_regression")

    results = {}

    for model, key in zip(models, api_keys):
        os.environ["LLM_BASE_URL"] = base_url
        os.environ["LLM_API_KEY"] = key
        os.environ["LLM_MODEL"] = model
        os.environ["SLOSCOPE_CONTEXT_TYPE"] = "service"

        start = time.perf_counter()
        try:
            report = classify(drift_signal)
            elapsed = time.perf_counter() - start

            schema_valid = is_valid(report, "drift-report")
            classification_correct = report.get("classification") == expected_class
            has_remediation = any(
                r.get("remediation_plan") for r in report.get("recommendations", [])
            )

            results[model] = {
                "status": "pass" if schema_valid and classification_correct else "fail",
                "latency_s": round(elapsed, 2),
                "schema_valid": schema_valid,
                "classification": report.get("classification"),
                "expected": expected_class,
                "classification_correct": classification_correct,
                "severity": report.get("severity"),
                "recommendations": len(report.get("recommendations", [])),
                "has_remediation_plan": has_remediation,
            }
        except Exception as e:
            elapsed = time.perf_counter() - start
            results[model] = {
                "status": "error",
                "latency_s": round(elapsed, 2),
                "error": str(e)[:120],
            }

    return results


def get_environment():
    """Capture the benchmark environment."""
    go_version = "unknown"
    try:
        result = subprocess.run(["go", "version"], capture_output=True, text=True)
        go_version = result.stdout.strip().split()[2] if result.returncode == 0 else "unknown"
    except Exception:
        pass

    return {
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "go_version": go_version,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main():
    parser = argparse.ArgumentParser(description="sloscope benchmark suite")
    parser.add_argument("--live", action="store_true", help="Include live LLM tests")
    parser.add_argument("--models", default="qwen3-235b", help="Comma-separated model list")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "benchmark-results.json"), help="Output path")
    args = parser.parse_args()

    results = {
        "environment": get_environment(),
    }

    print("=== sloscope benchmark suite ===\n")

    # 1. Baseline computation
    print("1. Benchmarking baseline computation...")
    results["baseline_computation"] = benchmark_baseline_computation()
    for name, r in results["baseline_computation"].items():
        if isinstance(r, dict) and "mean_ms" in r:
            print(f"   {name}: {r['mean_ms']}ms avg ({r['min_ms']}-{r['max_ms']}ms), deterministic={r['deterministic']}")

    # 2. Deviation computation
    print("\n2. Benchmarking deviation computation...")
    results["deviation_computation"] = benchmark_deviation_computation()
    for name, r in results["deviation_computation"].items():
        if isinstance(r, dict) and "mean_ms" in r:
            print(f"   {name}: {r['mean_ms']}ms avg, class={r['dominant_class']}, breached={r['breached_count']}")

    # 3. Eval grids
    print("\n3. Running eval grids...")
    results["eval_grids"] = benchmark_eval_grid()
    for grid_name, r in results["eval_grids"].items():
        if "total_scenarios" in r:
            print(f"   {grid_name}: {r['passed']}/{r['total_scenarios']} passed in {r['eval_time_ms']}ms")

    # 4. E2E pipeline
    print("\n4. Benchmarking E2E pipeline...")
    results["e2e_pipeline"] = benchmark_e2e_pipeline()
    for k, v in results["e2e_pipeline"].items():
        if k.endswith("_ms"):
            print(f"   {k}: {v}ms")

    # 5. Live LLM tests (optional)
    if args.live:
        base_url = os.environ.get("LLM_BASE_URL", "https://litellm.example.com/v1")
        models = args.models.split(",")

        # Map models to API keys by tier
        model_keys = {}
        cpu_key = os.environ.get("SLOSCOPE_CPU_KEY", "")
        gpu_key = os.environ.get("SLOSCOPE_GPU_KEY", "")
        api_key = os.environ.get("SLOSCOPE_API_KEY", os.environ.get("LLM_API_KEY", ""))

        CPU_MODELS = {"granite-3-2-8b-instruct-cpu", "granite-2b-cpu", "granite-4-0-h-tiny-cpu", "phi3-mini-cpu", "qwen25-3b-cpu"}
        GPU_MODELS = {"granite-3-2-8b-instruct", "granite-4-0-h-tiny", "microsoft-phi-4", "llama-scout-17b", "qwen3-14b", "deepseek-r1-distill-qwen-14b", "gpt-oss-120b", "gpt-oss-20b"}
        API_MODELS = {"qwen3-235b", "claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"}

        api_keys = []
        for m in models:
            if m in CPU_MODELS:
                api_keys.append(cpu_key)
            elif m in GPU_MODELS:
                api_keys.append(gpu_key)
            else:
                api_keys.append(api_key)

        if all(api_keys):
            print(f"\n5. Live LLM proposal test ({', '.join(models)})...")
            results["llm_proposal"] = benchmark_llm_proposal(models, api_keys, base_url)
            for model, r in results["llm_proposal"].items():
                print(f"   {model}: pass_rate={r['pass_rate']}, avg_latency={r['avg_latency_s']}s")

            print(f"\n6. Live LLM drift test ({', '.join(models)})...")
            results["llm_drift"] = benchmark_llm_drift(models, api_keys, base_url)
            for model, r in results["llm_drift"].items():
                print(f"   {model}: {r['status']}, class={r.get('classification','?')}, latency={r['latency_s']}s")
        else:
            print("\n5-6. Skipping live LLM tests (set SLOSCOPE_API_KEY/GPU_KEY/CPU_KEY)")
            results["llm_proposal"] = {"status": "skip", "reason": "no API keys"}
            results["llm_drift"] = {"status": "skip", "reason": "no API keys"}

    # Write results
    output_path = args.output
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)

    print(f"\nResults written to {output_path}")

    # Summary
    print("\n=== Summary ===")
    bl = results.get("baseline_computation", {})
    if "metrics_only" in bl:
        print(f"Baseline (metrics): {bl['metrics_only']['mean_ms']}ms")
    if "full_evidence" in bl:
        print(f"Baseline (full): {bl['full_evidence']['mean_ms']}ms")

    ev = results.get("eval_grids", {})
    if "proposal_eval" in ev and "passed" in ev["proposal_eval"]:
        print(f"Proposal eval: {ev['proposal_eval']['passed']}/{ev['proposal_eval']['total_scenarios']}")
    if "drift_eval" in ev and "passed" in ev["drift_eval"]:
        print(f"Drift eval: {ev['drift_eval']['passed']}/{ev['drift_eval']['total_scenarios']}")

    e2e = results.get("e2e_pipeline", {})
    if "generate_dry_run_ms" in e2e:
        print(f"Generate dry-run: {e2e['generate_dry_run_ms']}ms")
    if "drift_dry_run_ms" in e2e:
        print(f"Drift dry-run: {e2e['drift_dry_run_ms']}ms")


if __name__ == "__main__":
    main()
