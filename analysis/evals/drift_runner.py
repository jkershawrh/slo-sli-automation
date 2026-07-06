"""Eval suite runner for the LLM drift classification and remediation stage."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.drift_rubric import evaluate_drift_report

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "drift"
RECORDED_DIR = Path(__file__).parent / "recorded" / "drift"
GROUND_TRUTH_PATH = FIXTURES_DIR / "ground_truth.json"

DRIFT_SCENARIOS = [
    "latency_regression",
    "latency_improvement",
    "error_rate_elevation",
    "error_rate_reduction",
    "throughput_collapse",
    "throughput_surge",
    "saturation_approach",
    "availability_drop",
    "distribution_shift",
    "no_significant_drift",
]


def load_ground_truth():
    """Load the ground-truth manifest."""
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def load_drift_fixture(name):
    """Load a drift-signal fixture by name."""
    path = FIXTURES_DIR / "{}.json".format(name)
    with open(path) as f:
        return json.load(f)


def load_drift_recorded_response(name):
    """Load a recorded LLM drift response by scenario name."""
    path = RECORDED_DIR / "{}_response.json".format(name)
    with open(path) as f:
        return json.load(f)


def run_drift_eval_suite():
    """Run the full drift eval suite and return the grid."""
    ground_truth = load_ground_truth()
    grid = {}

    for scenario in DRIFT_SCENARIOS:
        drift_signal = load_drift_fixture(scenario)
        gt = ground_truth.get(scenario)
        if gt is None:
            grid[scenario] = {"error": "No ground truth found for {}".format(scenario)}
            continue

        try:
            response = load_drift_recorded_response(scenario)
        except FileNotFoundError:
            grid[scenario] = {"error": "No recorded response found for {}".format(scenario)}
            continue

        grid[scenario] = evaluate_drift_report(response, drift_signal, gt)

    return grid


def print_drift_grid(grid):
    """Pretty-print the drift eval grid."""
    all_pass = True
    for case, result in grid.items():
        status = "GREEN" if result.get("pass") else "RED"
        if not result.get("pass"):
            all_pass = False
        print("\n{}: {}".format(case, status))
        if "error" in result:
            print("  ERROR: {}".format(result["error"]))
            continue
        if "hard_gates" in result:
            for gate, passed in result["hard_gates"].items():
                mark = "PASS" if passed else "FAIL"
                print("  Hard gate - {}: {}".format(gate, mark))
        if "scored_dimensions" in result:
            for dim, passed in result["scored_dimensions"].items():
                mark = "PASS" if passed else "FAIL"
                print("  Scored   - {}: {}".format(dim, mark))

    print("\nOverall: {}".format("GREEN" if all_pass else "RED"))
    return all_pass


if __name__ == "__main__":
    grid = run_drift_eval_suite()
    passed = print_drift_grid(grid)
    exit(0 if passed else 1)
