"""TDD tests for deterministic baseline computation.

All expected values are hand-computed from the evidence fixtures using
the Prometheus histogram_quantile algorithm (linear interpolation).
"""

import copy
import json
import math
from pathlib import Path

import pytest

from baseline import compute_baseline, compute_percentile_from_histogram, compute_stddev_from_histogram
from schemas.validate import is_valid, validate
from serialize import serialize

TESTDATA_DIR = Path(__file__).resolve().parent.parent.parent / "testdata"


def _load_fixture(name):
    path = TESTDATA_DIR / name
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Hand-computed expected values for checkout-api evidence fixture
# ---------------------------------------------------------------------------
# Histogram buckets (cumulative):
#   le=0.005  count=100
#   le=0.01   count=500
#   le=0.025  count=2000
#   le=0.05   count=5000
#   le=0.1    count=15000
#   le=0.25   count=40000
#   le=0.5    count=70000
#   le=1.0    count=85000
#   le=2.5    count=95000
#   le=5.0    count=99000
#   le=10.0   count=99800
#   le=+Inf   count=100000
# total_count=100000, sum=42000.0
#
# Percentile algorithm: rank = q * total_count
# Find bucket where cumulative count >= rank, interpolate linearly.
#
# p50: rank=50000, falls in le=0.5 bucket (prev: count=40000,bound=0.25)
#   fraction = (50000-40000)/(70000-40000) = 10000/30000 = 1/3
#   value = 0.25 + 1/3 * (0.5 - 0.25) = 0.25 + 0.08333... = 0.33333... s = 333.333 ms
#
# p90: rank=90000, falls in le=2.5 bucket (prev: count=85000,bound=1.0)
#   fraction = (90000-85000)/(95000-85000) = 5000/10000 = 0.5
#   value = 1.0 + 0.5 * (2.5 - 1.0) = 1.0 + 0.75 = 1.75 s = 1750 ms
#
# p95: rank=95000, falls in le=2.5 bucket (count=95000 >= 95000)
#   fraction = (95000-85000)/(95000-85000) = 1.0
#   value = 1.0 + 1.0 * 1.5 = 2.5 s = 2500 ms
#
# p99: rank=99000, falls in le=5.0 bucket (prev: count=95000,bound=2.5)
#   fraction = (99000-95000)/(99000-95000) = 1.0
#   value = 2.5 + 1.0 * 2.5 = 5.0 s = 5000 ms
#
# stddev: mean=42000/100000=0.42s, bucket midpoints, variance via sum(count_i*(mid_i-mean)^2)/N
#   stddev ~= 1356.37 ms (6 sig digits)
#
# Error rate: 230/100000 = 0.0023, binomial stddev = sqrt(0.0023*0.9977/100000) ~= 0.000151483
# Availability: 1 - 0.0023 = 0.9977
#
# Throughput (30 rate_samples):
#   mean = 100.7/30 = 3.35667
#   sorted values p95 = index 28 (0-based) = 4.2
#   stddev ~= 0.444735
#
# Saturation:
#   CPU samples [0.32,0.35,0.41,0.38,0.29,0.72,0.45,0.33,0.36,0.40]
#     mean=0.401, p95=0.72
#   Memory samples [0.58,0.61,0.63,0.59,0.65,0.78,0.62,0.60,0.64,0.61]
#     mean=0.631, p95=0.78

EXPECTED_P50_MS = 333.333
EXPECTED_P90_MS = 1750.0
EXPECTED_P95_MS = 2500.0
EXPECTED_P99_MS = 5000.0
EXPECTED_STDDEV_MS = 1356.37
EXPECTED_ERROR_RATIO = 0.0023
EXPECTED_ERROR_STDDEV = 0.000151483
EXPECTED_AVAILABILITY = 0.9977
EXPECTED_THROUGHPUT_MEAN = 3.35667
EXPECTED_THROUGHPUT_P95 = 4.2
EXPECTED_THROUGHPUT_STDDEV = 0.444735
EXPECTED_CPU_MEAN = 0.401
EXPECTED_CPU_P95 = 0.72
EXPECTED_MEM_MEAN = 0.631
EXPECTED_MEM_P95 = 0.78


class TestPercentileFromHistogram:
    """Unit tests for the histogram percentile algorithm."""

    def setup_method(self):
        self.evidence = _load_fixture("evidence_checkout_api.json")
        self.buckets = self.evidence["series"]["latency_histogram"]["buckets"]
        self.total = self.evidence["series"]["latency_histogram"]["total_count"]

    def test_p50(self):
        result = compute_percentile_from_histogram(self.buckets, self.total, 0.50)
        # p50 = 0.33333... seconds
        assert result == pytest.approx(1.0 / 3.0, rel=1e-6)

    def test_p90(self):
        result = compute_percentile_from_histogram(self.buckets, self.total, 0.90)
        assert result == pytest.approx(1.75, rel=1e-6)

    def test_p95(self):
        result = compute_percentile_from_histogram(self.buckets, self.total, 0.95)
        assert result == pytest.approx(2.5, rel=1e-6)

    def test_p99(self):
        result = compute_percentile_from_histogram(self.buckets, self.total, 0.99)
        assert result == pytest.approx(5.0, rel=1e-6)


class TestStddevFromHistogram:
    """Unit tests for histogram standard deviation estimation."""

    def setup_method(self):
        self.evidence = _load_fixture("evidence_checkout_api.json")
        hist = self.evidence["series"]["latency_histogram"]
        self.buckets = hist["buckets"]
        self.total = hist["total_count"]
        self.hist_sum = hist["sum"]

    def test_stddev(self):
        result = compute_stddev_from_histogram(self.buckets, self.total, self.hist_sum)
        # stddev in seconds ~= 1.35637 s => 1356.37 ms
        assert result * 1000 == pytest.approx(EXPECTED_STDDEV_MS, rel=1e-4)


class TestCheckoutApiBaseline:
    """Integration tests: compute baseline from checkout-api evidence and verify all values."""

    def setup_method(self):
        self.evidence = _load_fixture("evidence_checkout_api.json")
        self.baseline = compute_baseline(self.evidence)

    # -- Schema metadata --

    def test_schema_version(self):
        assert self.baseline["schema_version"] == 1

    def test_service(self):
        assert self.baseline["service"] == "checkout-api"

    def test_namespace(self):
        assert self.baseline["namespace"] == "payments"

    def test_lookback_window(self):
        assert self.baseline["lookback_window"] == "30d"

    def test_generated_at(self):
        assert self.baseline["generated_at"] == "2026-07-05T12:00:00Z"

    # -- Latency indicators --

    def test_latency_p50(self):
        assert self.baseline["indicators"]["latency"]["p50_ms"] == pytest.approx(
            EXPECTED_P50_MS, rel=1e-4
        )

    def test_latency_p90(self):
        assert self.baseline["indicators"]["latency"]["p90_ms"] == pytest.approx(
            EXPECTED_P90_MS, rel=1e-4
        )

    def test_latency_p95(self):
        assert self.baseline["indicators"]["latency"]["p95_ms"] == pytest.approx(
            EXPECTED_P95_MS, rel=1e-4
        )

    def test_latency_p99(self):
        assert self.baseline["indicators"]["latency"]["p99_ms"] == pytest.approx(
            EXPECTED_P99_MS, rel=1e-4
        )

    def test_latency_stddev(self):
        assert self.baseline["indicators"]["latency"]["stddev_ms"] == pytest.approx(
            EXPECTED_STDDEV_MS, rel=1e-3
        )

    def test_latency_sample_count(self):
        assert self.baseline["indicators"]["latency"]["sample_count"] == 100000

    def test_latency_source_query(self):
        assert "histogram_quantile" in self.baseline["indicators"]["latency"]["source_query"]

    # -- Error rate indicators --

    def test_error_ratio(self):
        assert self.baseline["indicators"]["error_rate"]["ratio"] == pytest.approx(
            EXPECTED_ERROR_RATIO, rel=1e-6
        )

    def test_error_stddev(self):
        assert self.baseline["indicators"]["error_rate"]["stddev"] == pytest.approx(
            EXPECTED_ERROR_STDDEV, rel=1e-3
        )

    def test_error_count(self):
        assert self.baseline["indicators"]["error_rate"]["error_count"] == 230

    def test_error_total_count(self):
        assert self.baseline["indicators"]["error_rate"]["total_count"] == 100000

    # -- Availability --

    def test_availability_ratio(self):
        assert self.baseline["indicators"]["availability"]["ratio"] == pytest.approx(
            EXPECTED_AVAILABILITY, rel=1e-6
        )

    def test_availability_definition(self):
        assert "error_count" in self.baseline["indicators"]["availability"]["definition"]

    # -- Throughput --

    def test_throughput_mean(self):
        assert self.baseline["indicators"]["throughput"]["mean_rps"] == pytest.approx(
            EXPECTED_THROUGHPUT_MEAN, rel=1e-4
        )

    def test_throughput_p95(self):
        assert self.baseline["indicators"]["throughput"]["p95_rps"] == pytest.approx(
            EXPECTED_THROUGHPUT_P95, rel=1e-6
        )

    def test_throughput_stddev(self):
        assert self.baseline["indicators"]["throughput"]["stddev_rps"] == pytest.approx(
            EXPECTED_THROUGHPUT_STDDEV, rel=1e-3
        )

    def test_throughput_sample_count(self):
        assert self.baseline["indicators"]["throughput"]["sample_count"] == 30

    # -- Saturation --

    def test_saturation_available(self):
        assert self.baseline["indicators"]["saturation"]["available"] is True

    def test_saturation_cpu_mean(self):
        assert self.baseline["indicators"]["saturation"]["cpu_mean_ratio"] == pytest.approx(
            EXPECTED_CPU_MEAN, rel=1e-4
        )

    def test_saturation_cpu_p95(self):
        assert self.baseline["indicators"]["saturation"]["cpu_p95_ratio"] == pytest.approx(
            EXPECTED_CPU_P95, rel=1e-6
        )

    def test_saturation_memory_mean(self):
        assert self.baseline["indicators"]["saturation"]["memory_mean_ratio"] == pytest.approx(
            EXPECTED_MEM_MEAN, rel=1e-4
        )

    def test_saturation_memory_p95(self):
        assert self.baseline["indicators"]["saturation"]["memory_p95_ratio"] == pytest.approx(
            EXPECTED_MEM_P95, rel=1e-6
        )

    # -- Provenance --

    def test_provenance_endpoint(self):
        assert "thanos-querier" in self.baseline["provenance"]["prometheus_endpoint"]

    def test_provenance_timestamps(self):
        assert self.baseline["provenance"]["query_timestamps"]["start"] == "2026-06-05T12:00:00Z"
        assert self.baseline["provenance"]["query_timestamps"]["end"] == "2026-07-05T12:00:00Z"

    def test_provenance_coverage_ratio(self):
        assert self.baseline["provenance"]["coverage_ratio"] == 0.97


class TestSchemaValidation:
    """Verify that computed baselines conform to the baseline schema."""

    def test_checkout_api_validates_against_schema(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        baseline = compute_baseline(evidence)
        # Should not raise
        validate(baseline, "baseline")

    def test_empty_fixture_validates_against_schema(self):
        evidence = _load_fixture("evidence_empty.json")
        baseline = compute_baseline(evidence)
        validate(baseline, "baseline")

    def test_is_valid_returns_true(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        baseline = compute_baseline(evidence)
        assert is_valid(baseline, "baseline")


class TestDeterminism:
    """Verify byte-for-byte reproducibility of baseline output."""

    def test_identical_output_on_repeated_calls(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        baseline1 = compute_baseline(evidence)
        baseline2 = compute_baseline(evidence)

        output1 = serialize(baseline1)
        output2 = serialize(baseline2)

        assert output1 == output2, "Baseline output must be byte-for-byte identical across calls"

    def test_identical_output_with_deep_copy(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        evidence_copy = copy.deepcopy(evidence)

        baseline1 = compute_baseline(evidence)
        baseline2 = compute_baseline(evidence_copy)

        output1 = serialize(baseline1)
        output2 = serialize(baseline2)

        assert output1 == output2, "Deep-copied input must produce identical output"

    def test_output_has_sorted_keys(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        baseline = compute_baseline(evidence)
        output = serialize(baseline)
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

    def test_output_ends_with_newline(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        baseline = compute_baseline(evidence)
        output = serialize(baseline)
        assert output.endswith("\n")


class TestMinimalEvidence:
    """Test with the minimal/empty evidence fixture."""

    def setup_method(self):
        self.evidence = _load_fixture("evidence_empty.json")
        self.baseline = compute_baseline(self.evidence)

    def test_service_name(self):
        assert self.baseline["service"] == "minimal-service"

    def test_namespace(self):
        assert self.baseline["namespace"] == "default"

    def test_error_ratio_zero(self):
        assert self.baseline["indicators"]["error_rate"]["ratio"] == 0.0

    def test_availability_one(self):
        assert self.baseline["indicators"]["availability"]["ratio"] == 1.0

    def test_no_saturation(self):
        assert "saturation" not in self.baseline["indicators"]

    def test_throughput_sample_count(self):
        assert self.baseline["indicators"]["throughput"]["sample_count"] == 3

    def test_validates_against_schema(self):
        validate(self.baseline, "baseline")


class TestInvalidEvidence:
    """Test error handling for invalid or incomplete evidence."""

    def test_missing_series_raises_error(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        del evidence["series"]
        with pytest.raises(Exception):
            compute_baseline(evidence)

    def test_missing_latency_histogram_raises_error(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        del evidence["series"]["latency_histogram"]
        with pytest.raises(Exception):
            compute_baseline(evidence)

    def test_missing_request_total_raises_error(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        del evidence["series"]["request_total"]
        with pytest.raises(Exception):
            compute_baseline(evidence)

    def test_missing_error_total_raises_error(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        del evidence["series"]["error_total"]
        with pytest.raises(Exception):
            compute_baseline(evidence)

    def test_invalid_schema_version_raises_error(self):
        evidence = _load_fixture("evidence_checkout_api.json")
        evidence["schema_version"] = 99
        with pytest.raises(Exception):
            compute_baseline(evidence)

    def test_completely_empty_dict_raises_error(self):
        with pytest.raises(Exception):
            compute_baseline({})


class TestSerializeCanonical:
    """Tests for the canonical serializer."""

    def test_float_formatting_six_sig_digits(self):
        data = {"value": 3.3566666666666667}
        output = serialize(data)
        parsed = json.loads(output)
        assert parsed["value"] == 3.35667

    def test_float_zero(self):
        data = {"value": 0.0}
        output = serialize(data)
        parsed = json.loads(output)
        assert parsed["value"] == 0.0

    def test_float_no_trailing_zeros(self):
        data = {"value": 4.20000}
        output = serialize(data)
        # 4.2 with 6 sig digits = 4.2
        parsed = json.loads(output)
        assert parsed["value"] == 4.2

    def test_nan_raises_error(self):
        data = {"value": float("nan")}
        with pytest.raises(ValueError):
            serialize(data)

    def test_inf_raises_error(self):
        data = {"value": float("inf")}
        with pytest.raises(ValueError):
            serialize(data)

    def test_sorted_keys(self):
        data = {"zebra": 1, "apple": 2, "mango": 3}
        output = serialize(data)
        keys = list(json.loads(output).keys())
        assert keys == ["apple", "mango", "zebra"]

    def test_two_space_indent(self):
        data = {"a": {"b": 1}}
        output = serialize(data)
        assert '  "a"' in output
        assert '    "b"' in output

    def test_trailing_newline(self):
        output = serialize({"x": 1})
        assert output.endswith("\n")
        assert not output.endswith("\n\n")
