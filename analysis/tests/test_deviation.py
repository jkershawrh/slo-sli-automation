"""TDD tests for deterministic deviation computation and rule-based classification.

All expected values are hand-computed from the drift test fixtures using
the same baseline computation algorithm as baseline.py.

Regression fixture expected live values (from compute_baseline):
  latency_p99_ms = 5000.0    (baseline: 500.0,  stddev: 100.0)
  latency_p50_ms = 500.0     (baseline: 180.0,  stddev: 100.0)
  error_rate     = 0.0025    (baseline: 0.002,   stddev: 0.0005)
  availability   = 0.9975    (baseline: 0.998,   stddev: 0.0005)
  throughput     = 5.41667   (baseline: 5.0,     stddev: 1.2)
  cpu_mean       = 0.48      (baseline: 0.4,     stddev: 0.1)
  memory_mean    = 0.643     (baseline: 0.6,     stddev: 0.1)

Tolerance bands = baseline +/- 2*stddev.
Breached in regression fixture: latency_p99_ms (mag 22.5), latency_p50_ms (mag 1.6).
Dominant signal: latency_p99_ms -> latency_regression.

No-drift fixture: all indicators within bands, dominant = no_significant_drift.
"""

import copy
import json
import math
from pathlib import Path

import pytest

from baseline import compute_baseline
from deviation import (
    BAND_MULTIPLIER,
    EPSILON,
    classify_indicator,
    compute_deviation,
    compute_drift_signal,
)
from schemas.validate import is_valid, validate
from serialize import serialize

TESTDATA_DIR = Path(__file__).resolve().parent.parent.parent / "testdata"


def _load_fixture(name):
    path = TESTDATA_DIR / name
    with open(path) as f:
        return json.load(f)


def _make_combined_input(evidence_name, baseline_name="drift_baseline_reference.json"):
    return {
        "live_evidence": _load_fixture(evidence_name),
        "baseline": _load_fixture(baseline_name),
    }


# ---------------------------------------------------------------------------
# Unit tests: deviation math
# ---------------------------------------------------------------------------


class TestComputeDeviationPositive:
    """test_compute_deviation_positive: live > baseline."""

    def test_abs_deviation(self):
        result = compute_deviation(5000.0, 500.0, 100.0, "ms")
        assert result["abs_deviation"] == pytest.approx(4500.0, rel=1e-6)

    def test_direction_increasing(self):
        result = compute_deviation(5000.0, 500.0, 100.0, "ms")
        assert result["direction"] == "increasing"

    def test_rel_deviation_positive(self):
        result = compute_deviation(5000.0, 500.0, 100.0, "ms")
        assert result["rel_deviation"] == pytest.approx(9.0, rel=1e-6)


class TestComputeDeviationNegative:
    """test_compute_deviation_negative: live < baseline."""

    def test_abs_deviation_still_positive(self):
        result = compute_deviation(300.0, 500.0, 100.0, "ms")
        assert result["abs_deviation"] == pytest.approx(200.0, rel=1e-6)

    def test_direction_decreasing(self):
        result = compute_deviation(300.0, 500.0, 100.0, "ms")
        assert result["direction"] == "decreasing"

    def test_rel_deviation_negative(self):
        result = compute_deviation(300.0, 500.0, 100.0, "ms")
        assert result["rel_deviation"] == pytest.approx(-0.4, rel=1e-6)


class TestComputeDeviationZero:
    """test_compute_deviation_zero: live == baseline."""

    def test_zero_deviation(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["abs_deviation"] == 0.0

    def test_stable_direction(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["direction"] == "stable"

    def test_zero_rel_deviation(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["rel_deviation"] == 0.0


class TestRelativeDeviationNearZeroBaseline:
    """test_relative_deviation_near_zero_baseline: stabilized formula with epsilon."""

    def test_uses_epsilon_for_zero_baseline(self):
        # For ratio type: epsilon = 0.001
        # baseline = 0.0, live = 0.001
        # denominator = max(|0.0|, 0.001) = 0.001
        # rel_dev = (0.001 - 0.0) / 0.001 = 1.0
        result = compute_deviation(0.001, 0.0, 0.0001, "ratio")
        assert result["rel_deviation"] == pytest.approx(1.0, rel=1e-6)

    def test_uses_epsilon_for_near_zero_baseline(self):
        # baseline = 0.0001, epsilon_ratio = 0.001
        # denominator = max(0.0001, 0.001) = 0.001
        result = compute_deviation(0.002, 0.0001, 0.0001, "ratio")
        expected_rel = (0.002 - 0.0001) / 0.001
        assert result["rel_deviation"] == pytest.approx(expected_rel, rel=1e-6)

    def test_ms_epsilon_is_1(self):
        # baseline = 0.5ms, epsilon_ms = 1.0
        # denominator = max(0.5, 1.0) = 1.0
        result = compute_deviation(2.0, 0.5, 0.1, "ms")
        expected_rel = (2.0 - 0.5) / 1.0
        assert result["rel_deviation"] == pytest.approx(expected_rel, rel=1e-6)

    def test_no_infinite_deviation(self):
        # Even with baseline = 0, should not produce inf
        result = compute_deviation(0.005, 0.0, 0.001, "ratio")
        assert not math.isinf(result["rel_deviation"])
        assert not math.isnan(result["rel_deviation"])


class TestToleranceBandComputation:
    """test_tolerance_band_computation: band = baseline +/- 2*stddev."""

    def test_band_upper(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["band_upper"] == pytest.approx(700.0, rel=1e-6)

    def test_band_lower(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["band_lower"] == pytest.approx(300.0, rel=1e-6)

    def test_band_width(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        width = result["band_upper"] - result["band_lower"]
        assert width == pytest.approx(400.0, rel=1e-6)

    def test_custom_band_values(self):
        # baseline=0.002, stddev=0.0005 -> band=[0.001, 0.003]
        result = compute_deviation(0.002, 0.002, 0.0005, "ratio")
        assert result["band_upper"] == pytest.approx(0.003, rel=1e-6)
        assert result["band_lower"] == pytest.approx(0.001, rel=1e-6)


class TestBandBreachAbove:
    """test_band_breach_above: live > band_upper = breach."""

    def test_breach_above(self):
        # baseline=500, stddev=100, band_upper=700
        result = compute_deviation(800.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is True

    def test_breach_magnitude_positive(self):
        result = compute_deviation(800.0, 500.0, 100.0, "ms")
        # abs_dev=300, band_width=400, half=200, magnitude=300/200=1.5
        assert result["breach_magnitude"] == pytest.approx(1.5, rel=1e-6)


class TestBandBreachBelow:
    """test_band_breach_below: live < band_lower = breach."""

    def test_breach_below(self):
        # baseline=500, stddev=100, band_lower=300
        result = compute_deviation(200.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is True

    def test_breach_magnitude_below(self):
        result = compute_deviation(200.0, 500.0, 100.0, "ms")
        # abs_dev=300, band_width=400, half=200, magnitude=300/200=1.5
        assert result["breach_magnitude"] == pytest.approx(1.5, rel=1e-6)


class TestBandNoBreach:
    """test_band_no_breach: live within bands = no breach."""

    def test_no_breach_center(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is False

    def test_no_breach_near_upper(self):
        result = compute_deviation(699.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is False

    def test_no_breach_near_lower(self):
        result = compute_deviation(301.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is False

    def test_no_breach_at_upper_boundary(self):
        result = compute_deviation(700.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is False

    def test_no_breach_at_lower_boundary(self):
        result = compute_deviation(300.0, 500.0, 100.0, "ms")
        assert result["band_breach"] is False

    def test_no_breach_magnitude_zero(self):
        result = compute_deviation(500.0, 500.0, 100.0, "ms")
        assert result["breach_magnitude"] == 0.0


# ---------------------------------------------------------------------------
# Unit tests: rule-based classifier
# ---------------------------------------------------------------------------


class TestClassifyLatencyRegression:
    """test_classify_latency_regression: latency increasing + breach."""

    def test_p99_latency_regression(self):
        result = classify_indicator("latency_p99_ms", "increasing", True)
        assert result == "latency_regression"

    def test_p50_latency_regression(self):
        result = classify_indicator("latency_p50_ms", "increasing", True)
        assert result == "latency_regression"


class TestClassifyLatencyImprovement:
    """test_classify_latency_improvement: latency decreasing + breach."""

    def test_p99_latency_improvement(self):
        result = classify_indicator("latency_p99_ms", "decreasing", True)
        assert result == "latency_improvement"

    def test_p50_latency_improvement(self):
        result = classify_indicator("latency_p50_ms", "decreasing", True)
        assert result == "latency_improvement"


class TestClassifyErrorRateElevation:
    """test_classify_error_rate_elevation: error_rate increasing + breach."""

    def test_error_rate_elevation(self):
        result = classify_indicator("error_rate_ratio", "increasing", True)
        assert result == "error_rate_elevation"


class TestClassifyErrorRateReduction:
    """test_classify_error_rate_reduction: error_rate decreasing + breach."""

    def test_error_rate_reduction(self):
        result = classify_indicator("error_rate_ratio", "decreasing", True)
        assert result == "error_rate_reduction"


class TestClassifyThroughputCollapse:
    """test_classify_throughput_collapse: throughput decreasing + breach."""

    def test_throughput_collapse(self):
        result = classify_indicator("throughput_mean_rps", "decreasing", True)
        assert result == "throughput_collapse"


class TestClassifyThroughputSurge:
    """test_classify_throughput_surge: throughput increasing + breach."""

    def test_throughput_surge(self):
        result = classify_indicator("throughput_mean_rps", "increasing", True)
        assert result == "throughput_surge"


class TestClassifyNoDrift:
    """test_classify_no_drift: no breach = no_significant_drift."""

    def test_no_drift_latency(self):
        result = classify_indicator("latency_p99_ms", "increasing", False)
        assert result == "no_significant_drift"

    def test_no_drift_error(self):
        result = classify_indicator("error_rate_ratio", "increasing", False)
        assert result == "no_significant_drift"

    def test_no_drift_throughput(self):
        result = classify_indicator("throughput_mean_rps", "decreasing", False)
        assert result == "no_significant_drift"

    def test_no_drift_stable(self):
        result = classify_indicator("latency_p99_ms", "stable", False)
        assert result == "no_significant_drift"


class TestClassifySaturationApproach:
    """test_classify_saturation_approach: CPU/memory increasing + breach."""

    def test_cpu_saturation_approach(self):
        result = classify_indicator("cpu_mean_ratio", "increasing", True)
        assert result == "saturation_approach"

    def test_memory_saturation_approach(self):
        result = classify_indicator("memory_mean_ratio", "increasing", True)
        assert result == "saturation_approach"

    def test_saturation_decreasing_no_drift(self):
        # Decreasing saturation is not considered drift
        result = classify_indicator("cpu_mean_ratio", "decreasing", True)
        assert result == "no_significant_drift"


# ---------------------------------------------------------------------------
# Unit tests: dominant signal
# ---------------------------------------------------------------------------


class TestDominantSignalSingleBreach:
    """test_dominant_signal_single_breach: one breach = that indicator is dominant."""

    def test_single_breach_is_dominant(self):
        combined = _make_combined_input("drift_live_no_drift.json")
        # Hack: force a single indicator to breach by adjusting baseline
        combined["baseline"]["indicators"]["throughput"]["mean_rps"] = 5.0
        combined["baseline"]["indicators"]["throughput"]["stddev_rps"] = 0.001
        # Now throughput will breach (live ~5.008 vs band [4.998, 5.002])
        signal = compute_drift_signal(combined)
        breached = signal["all_breached_indicators"]
        # throughput should be in breached indicators
        throughput_breached = [b for b in breached if "throughput" in b]
        assert len(throughput_breached) >= 1
        assert signal["dominant_signal"]["indicator"] in breached


class TestDominantSignalMultipleBreaches:
    """test_dominant_signal_multiple_breaches: dominant = largest normalized magnitude."""

    def test_latency_p99_dominates_p50(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        signal = compute_drift_signal(combined)

        # Both latency indicators breach, p99 has larger magnitude
        assert "latency_p99_ms" in signal["all_breached_indicators"]
        assert "latency_p50_ms" in signal["all_breached_indicators"]
        assert signal["dominant_signal"]["indicator"] == "latency_p99_ms"
        assert signal["dominant_signal"]["breach_magnitude"] > 1.0

    def test_dominant_has_largest_magnitude(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        signal = compute_drift_signal(combined)

        dom_mag = signal["dominant_signal"]["breach_magnitude"]
        for ind in signal["indicators"]:
            if ind.get("band_breach", False):
                # Compute magnitude from the indicator
                band_width = ind["band_upper"] - ind["band_lower"]
                if band_width > 0:
                    mag = ind["abs_deviation"] / (band_width / 2)
                    assert dom_mag >= mag - 1e-9


class TestDominantSignalNoBreach:
    """test_dominant_signal_no_breach: no breaches = no_significant_drift."""

    def test_no_breach_no_drift(self):
        combined = _make_combined_input("drift_live_no_drift.json")
        signal = compute_drift_signal(combined)
        assert signal["dominant_signal"]["class"] == "no_significant_drift"
        assert signal["dominant_signal"]["indicator"] == "none"
        assert signal["dominant_signal"]["breach_magnitude"] == 0.0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestLatencyRegressionFixture:
    """test_latency_regression_fixture: full computation against regression fixture."""

    def setup_method(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        self.signal = compute_drift_signal(combined)

    def test_service(self):
        assert self.signal["service"] == "checkout-api"

    def test_schema_version(self):
        assert self.signal["schema_version"] == 1

    def test_evaluation_window(self):
        assert self.signal["evaluation_window"] == "1h"

    def test_dominant_signal_class(self):
        assert self.signal["dominant_signal"]["class"] == "latency_regression"

    def test_dominant_signal_indicator(self):
        assert self.signal["dominant_signal"]["indicator"] == "latency_p99_ms"

    def test_dominant_breach_magnitude(self):
        # abs_dev=4500, band_width=400, half=200, magnitude=22.5
        assert self.signal["dominant_signal"]["breach_magnitude"] == pytest.approx(
            22.5, rel=1e-4
        )

    def test_breached_indicators(self):
        breached = self.signal["all_breached_indicators"]
        assert "latency_p99_ms" in breached
        assert "latency_p50_ms" in breached

    def test_latency_p99_indicator(self):
        p99 = next(
            i for i in self.signal["indicators"] if i["name"] == "latency_p99_ms"
        )
        assert p99["live_value"] == pytest.approx(5000.0, rel=1e-4)
        assert p99["baseline_value"] == pytest.approx(500.0, rel=1e-4)
        assert p99["abs_deviation"] == pytest.approx(4500.0, rel=1e-4)
        assert p99["rel_deviation"] == pytest.approx(9.0, rel=1e-4)
        assert p99["direction"] == "increasing"
        assert p99["band_upper"] == pytest.approx(700.0, rel=1e-4)
        assert p99["band_lower"] == pytest.approx(300.0, rel=1e-4)
        assert p99["band_breach"] is True
        assert p99["first_pass_class"] == "latency_regression"

    def test_latency_p50_indicator(self):
        p50 = next(
            i for i in self.signal["indicators"] if i["name"] == "latency_p50_ms"
        )
        assert p50["live_value"] == pytest.approx(500.0, rel=1e-4)
        assert p50["baseline_value"] == pytest.approx(180.0, rel=1e-4)
        assert p50["abs_deviation"] == pytest.approx(320.0, rel=1e-4)
        assert p50["direction"] == "increasing"
        assert p50["band_breach"] is True
        assert p50["first_pass_class"] == "latency_regression"

    def test_error_rate_within_band(self):
        er = next(
            i for i in self.signal["indicators"] if i["name"] == "error_rate_ratio"
        )
        assert er["band_breach"] is False
        assert er["first_pass_class"] == "no_significant_drift"

    def test_availability_within_band(self):
        av = next(
            i for i in self.signal["indicators"] if i["name"] == "availability_ratio"
        )
        assert av["band_breach"] is False
        assert av["first_pass_class"] == "no_significant_drift"

    def test_throughput_within_band(self):
        tp = next(
            i
            for i in self.signal["indicators"]
            if i["name"] == "throughput_mean_rps"
        )
        assert tp["band_breach"] is False
        assert tp["first_pass_class"] == "no_significant_drift"

    def test_saturation_indicators_present(self):
        names = [i["name"] for i in self.signal["indicators"]]
        assert "cpu_mean_ratio" in names
        assert "memory_mean_ratio" in names

    def test_saturation_within_band(self):
        cpu = next(
            i for i in self.signal["indicators"] if i["name"] == "cpu_mean_ratio"
        )
        assert cpu["band_breach"] is False

    def test_provenance(self):
        prov = self.signal["provenance"]
        assert "thanos-querier" in prov["prometheus_endpoint"]
        assert prov["coverage_ratio"] == pytest.approx(0.95, rel=1e-4)
        assert "start" in prov["query_timestamps"]
        assert "end" in prov["query_timestamps"]

    def test_indicator_count(self):
        # 5 core indicators + 2 saturation
        assert len(self.signal["indicators"]) == 7


class TestNoDriftFixture:
    """test_no_drift_fixture: full computation against no-drift fixture."""

    def setup_method(self):
        combined = _make_combined_input("drift_live_no_drift.json")
        self.signal = compute_drift_signal(combined)

    def test_dominant_no_drift(self):
        assert self.signal["dominant_signal"]["class"] == "no_significant_drift"

    def test_no_breached_indicators(self):
        assert len(self.signal["all_breached_indicators"]) == 0

    def test_all_indicators_no_drift(self):
        for ind in self.signal["indicators"]:
            if ind.get("status") != "skipped":
                assert ind["band_breach"] is False, (
                    "Expected no breach for {}, got breach. "
                    "live={}, band=[{},{}]".format(
                        ind["name"],
                        ind["live_value"],
                        ind["band_lower"],
                        ind["band_upper"],
                    )
                )
                assert ind["first_pass_class"] == "no_significant_drift"

    def test_latency_p99_within_band(self):
        p99 = next(
            i for i in self.signal["indicators"] if i["name"] == "latency_p99_ms"
        )
        assert p99["live_value"] == pytest.approx(500.0, rel=1e-4)
        assert p99["baseline_value"] == pytest.approx(500.0, rel=1e-4)
        assert p99["band_breach"] is False

    def test_service_name(self):
        assert self.signal["service"] == "checkout-api"


class TestOutputValidatesAgainstSchema:
    """test_output_validates_against_schema: output passes drift-signal schema."""

    def test_regression_validates(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        signal = compute_drift_signal(combined)
        validate(signal, "drift-signal")

    def test_no_drift_validates(self):
        combined = _make_combined_input("drift_live_no_drift.json")
        signal = compute_drift_signal(combined)
        validate(signal, "drift-signal")

    def test_is_valid_returns_true(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        signal = compute_drift_signal(combined)
        assert is_valid(signal, "drift-signal")


class TestDeterministicOutput:
    """test_deterministic_output: same input twice = byte-for-byte identical."""

    def test_regression_deterministic(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        signal1 = compute_drift_signal(combined)
        signal2 = compute_drift_signal(copy.deepcopy(combined))
        assert serialize(signal1) == serialize(signal2)

    def test_no_drift_deterministic(self):
        combined = _make_combined_input("drift_live_no_drift.json")
        signal1 = compute_drift_signal(combined)
        signal2 = compute_drift_signal(copy.deepcopy(combined))
        assert serialize(signal1) == serialize(signal2)

    def test_output_has_sorted_keys(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        signal = compute_drift_signal(combined)
        output = serialize(signal)
        parsed = json.loads(output)

        def check_sorted(obj, path=""):
            if isinstance(obj, dict):
                keys = list(obj.keys())
                assert keys == sorted(keys), "Keys not sorted at {}".format(path)
                for k, v in obj.items():
                    check_sorted(v, "{}.{}".format(path, k))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_sorted(item, "{}[{}]".format(path, i))

        check_sorted(parsed)


class TestSkippedIndicator:
    """test_skipped_indicator: unavailable saturation -> skipped status."""

    def test_saturation_skipped_when_unavailable(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        # Remove saturation from live evidence
        del combined["live_evidence"]["series"]["saturation"]
        signal = compute_drift_signal(combined)

        # Saturation indicators should be marked as skipped
        cpu_inds = [
            i for i in signal["indicators"] if i["name"] == "cpu_mean_ratio"
        ]
        mem_inds = [
            i for i in signal["indicators"] if i["name"] == "memory_mean_ratio"
        ]
        assert len(cpu_inds) == 1
        assert len(mem_inds) == 1
        assert cpu_inds[0].get("status") == "skipped"
        assert mem_inds[0].get("status") == "skipped"
        assert "skip_reason" in cpu_inds[0]
        assert "skip_reason" in mem_inds[0]

    def test_skipped_indicator_not_breached(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        del combined["live_evidence"]["series"]["saturation"]
        signal = compute_drift_signal(combined)

        cpu = next(
            i for i in signal["indicators"] if i["name"] == "cpu_mean_ratio"
        )
        assert cpu["band_breach"] is False
        assert cpu["first_pass_class"] == "no_significant_drift"

    def test_skipped_not_in_breached_list(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        del combined["live_evidence"]["series"]["saturation"]
        signal = compute_drift_signal(combined)

        assert "cpu_mean_ratio" not in signal["all_breached_indicators"]
        assert "memory_mean_ratio" not in signal["all_breached_indicators"]

    def test_output_still_validates(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        del combined["live_evidence"]["series"]["saturation"]
        signal = compute_drift_signal(combined)
        validate(signal, "drift-signal")

    def test_no_saturation_in_baseline_skips_gracefully(self):
        combined = _make_combined_input("drift_live_latency_regression.json")
        del combined["baseline"]["indicators"]["saturation"]
        signal = compute_drift_signal(combined)
        # Should have 5 core indicators only
        sat_inds = [
            i
            for i in signal["indicators"]
            if i["name"] in ("cpu_mean_ratio", "memory_mean_ratio")
        ]
        assert len(sat_inds) == 0
        validate(signal, "drift-signal")


# ---------------------------------------------------------------------------
# TDD tests for trace and log drift indicators
# ---------------------------------------------------------------------------


class TestTraceLogDeviation:
    """TDD tests for trace and log drift indicators."""

    def test_dependency_latency_regression_detected(self):
        """When a dependency p99 doubles, deviation should detect it."""
        baseline = self._load_full_baseline()
        live_evidence = self._load_fixture("drift_dependency_regression.json")
        signal = compute_drift_signal({"live_evidence": live_evidence, "baseline": baseline})

        # Find the trace indicator
        trace_ind = [i for i in signal["indicators"] if i["name"] == "dependency_p99_ms"]
        assert len(trace_ind) == 1
        assert trace_ind[0]["band_breach"] is True
        assert trace_ind[0]["first_pass_class"] == "dependency_latency_regression"

    def test_error_category_shift_detected(self):
        """When dominant error category ratio shifts significantly."""
        baseline = self._load_full_baseline()
        live_evidence = self._load_fixture("drift_error_category_shift.json")
        signal = compute_drift_signal({"live_evidence": live_evidence, "baseline": baseline})

        log_ind = [i for i in signal["indicators"] if i["name"] == "error_top_category_ratio"]
        assert len(log_ind) == 1
        assert log_ind[0]["band_breach"] is True
        assert log_ind[0]["first_pass_class"] == "error_category_shift"

    def test_no_trace_indicators_when_traces_unavailable(self):
        """Metrics-only evidence should produce no trace indicators."""
        # Use the original baseline without traces
        baseline_ref = json.load(open(TESTDATA_DIR / "drift_baseline_reference.json"))
        live = json.load(open(TESTDATA_DIR / "drift_live_no_drift.json"))
        signal = compute_drift_signal({"live_evidence": live, "baseline": baseline_ref})
        trace_inds = [i for i in signal["indicators"] if "dependency" in i["name"]]
        assert len(trace_inds) == 0

    def test_output_validates_with_new_classes(self):
        baseline = self._load_full_baseline()
        live = self._load_fixture("drift_dependency_regression.json")
        signal = compute_drift_signal({"live_evidence": live, "baseline": baseline})
        validate(signal, "drift-signal")

    def _load_full_baseline(self):
        with open(TESTDATA_DIR / "evidence_checkout_api_full.json") as f:
            return compute_baseline(json.load(f))

    def _load_fixture(self, name):
        with open(TESTDATA_DIR / name) as f:
            return json.load(f)
