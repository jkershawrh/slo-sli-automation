"""Eval suite runner for the LLM proposal stage."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.rubric import evaluate_proposal

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_DIR = Path(__file__).parent / "recorded"


def load_fixture(name):
    """Load a baseline fixture by name."""
    path = FIXTURES_DIR / "{}.json".format(name)
    with open(path) as f:
        return json.load(f)


def load_recorded_response(name):
    """Load a recorded LLM response by fixture name."""
    path = RECORDED_DIR / "{}_response.json".format(name)
    with open(path) as f:
        return json.load(f)


def run_eval_suite():
    """Run the full eval suite and return the grid."""
    fixtures = ["web_api_baseline", "high_traffic_baseline", "batch_processor_baseline", "web_api_baseline_full"]
    grid = {}

    for fixture_name in fixtures:
        baseline = load_fixture(fixture_name)
        try:
            proposal = load_recorded_response(fixture_name)
        except FileNotFoundError:
            grid[fixture_name] = {"error": "No recorded response found"}
            continue

        grid[fixture_name] = evaluate_proposal(proposal, baseline)

    return grid


def print_grid(grid):
    """Pretty-print the eval grid."""
    all_pass = True
    for case, result in grid.items():
        status = "GREEN" if result.get("pass") else "RED"
        if not result.get("pass"):
            all_pass = False
        print("\n{}: {}".format(case, status))
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
    grid = run_eval_suite()
    passed = print_grid(grid)
    exit(0 if passed else 1)
