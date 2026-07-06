"""Contract tests for drift-signal and drift-report JSON schemas."""

import copy
import json
from pathlib import Path

import pytest

from analysis.schemas.validate import is_valid, validate

TESTDATA_DIR = Path(__file__).resolve().parent.parent.parent / "testdata"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture(name):
    path = TESTDATA_DIR / name
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Valid drift-signal artifact used across tests
# ---------------------------------------------------------------------------

VALID_DRIFT_SIGNAL = {
    "schema_version": 1,
    "service": "checkout-api",
    "evaluation_window": "1h",
    "evaluated_at": "2026-07-06T14:00:00Z",
    "baseline_schema_version": 1,
    "indicators": [
        {
            "name": "latency_p99_ms",
            "live_value": 587.3,
            "baseline_value": 412.1,
            "abs_deviation": 175.2,
            "rel_deviation": 0.425,
            "direction": "increasing",
            "band_upper": 586.5,
            "band_lower": 237.7,
            "band_breach": True,
            "first_pass_class": "latency_regression"
        },
        {
            "name": "error_rate_ratio",
            "live_value": 0.0031,
            "baseline_value": 0.0023,
            "abs_deviation": 0.0008,
            "rel_deviation": 0.348,
            "direction": "increasing",
            "band_upper": 0.0039,
            "band_lower": 0.0007,
            "band_breach": False,
            "first_pass_class": "no_significant_drift"
        }
    ],
    "dominant_signal": {
        "indicator": "latency_p99_ms",
        "class": "latency_regression",
        "breach_magnitude": 1.003
    },
    "all_breached_indicators": ["latency_p99_ms"],
    "provenance": {
        "prometheus_endpoint": "https://thanos-querier.openshift-monitoring.svc:9091",
        "query_timestamps": {
            "start": "2026-07-06T13:00:00Z",
            "end": "2026-07-06T14:00:00Z"
        },
        "coverage_ratio": 0.98
    }
}


# ---------------------------------------------------------------------------
# Valid drift-report artifact used across tests
# ---------------------------------------------------------------------------

VALID_DRIFT_REPORT = {
    "schema_version": 1,
    "service": "checkout-api",
    "classification": "latency_regression",
    "severity": "high",
    "likely_cause": "Increased backend database query time following schema migration, evidenced by p99 latency rising from 412.1ms to 587.3ms (42.5% increase, breaching the 2-sigma band upper bound of 586.5ms).",
    "recommendations": [
        {
            "action": "Investigate database query performance for the checkout-api service, focusing on queries introduced or modified in the most recent deployment.",
            "confidence": "high",
            "rationale": "The latency p99 increased from 412.1ms baseline to 587.3ms live (abs_deviation 175.2ms, rel_deviation 42.5%), breaching the upper band of 586.5ms. Error rate remained within band (0.0031 vs baseline 0.0023), suggesting the issue is latency-specific rather than a general failure."
        }
    ]
}


# ---------------------------------------------------------------------------
# Drift-signal schema tests
# ---------------------------------------------------------------------------

class TestDriftSignalSchema:
    """Tests for drift-signal.schema.json."""

    def test_valid_drift_signal_validates(self):
        """A well-formed drift-signal artifact must validate."""
        validate(VALID_DRIFT_SIGNAL, "drift-signal")

    def test_invalid_taxonomy_class_rejected(self):
        """A first_pass_class not in the fixed taxonomy must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["indicators"][0]["first_pass_class"] = "memory_leak"
        assert not is_valid(data, "drift-signal")

    def test_invalid_dominant_signal_class_rejected(self):
        """A dominant_signal class not in the taxonomy must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["dominant_signal"]["class"] = "unknown_class"
        assert not is_valid(data, "drift-signal")

    def test_missing_required_field_service(self):
        """Missing top-level required field 'service' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        del data["service"]
        assert not is_valid(data, "drift-signal")

    def test_missing_required_field_indicators(self):
        """Missing top-level required field 'indicators' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        del data["indicators"]
        assert not is_valid(data, "drift-signal")

    def test_missing_required_field_dominant_signal(self):
        """Missing top-level required field 'dominant_signal' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        del data["dominant_signal"]
        assert not is_valid(data, "drift-signal")

    def test_missing_required_field_provenance(self):
        """Missing top-level required field 'provenance' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        del data["provenance"]
        assert not is_valid(data, "drift-signal")

    def test_missing_indicator_required_field(self):
        """An indicator missing a required field (band_breach) must be caught."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        del data["indicators"][0]["band_breach"]
        assert not is_valid(data, "drift-signal")

    def test_invalid_direction_enum(self):
        """A direction value outside the enum must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["indicators"][0]["direction"] = "sideways"
        assert not is_valid(data, "drift-signal")

    def test_negative_abs_deviation_rejected(self):
        """abs_deviation must be >= 0."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["indicators"][0]["abs_deviation"] = -1.0
        assert not is_valid(data, "drift-signal")

    def test_invalid_schema_version_rejected(self):
        """schema_version must be exactly 1."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["schema_version"] = 2
        assert not is_valid(data, "drift-signal")

    def test_invalid_evaluation_window_format(self):
        """evaluation_window must match the pattern ^[0-9]+[smhd]$."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["evaluation_window"] = "one hour"
        assert not is_valid(data, "drift-signal")

    def test_coverage_ratio_above_one_rejected(self):
        """coverage_ratio must be <= 1."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["provenance"]["coverage_ratio"] = 1.5
        assert not is_valid(data, "drift-signal")

    def test_additional_properties_rejected(self):
        """Extra top-level properties must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["extra_field"] = "should fail"
        assert not is_valid(data, "drift-signal")

    def test_skipped_indicator_validates(self):
        """An indicator with status=skipped and a skip_reason must validate."""
        data = copy.deepcopy(VALID_DRIFT_SIGNAL)
        data["indicators"].append({
            "name": "saturation_cpu",
            "live_value": 0,
            "baseline_value": 0.4,
            "abs_deviation": 0,
            "rel_deviation": 0,
            "direction": "stable",
            "band_upper": 0.6,
            "band_lower": 0.2,
            "band_breach": False,
            "first_pass_class": "no_significant_drift",
            "status": "skipped",
            "skip_reason": "Saturation metrics not available for this service"
        })
        validate(data, "drift-signal")


# ---------------------------------------------------------------------------
# Drift-report schema tests
# ---------------------------------------------------------------------------

class TestDriftReportSchema:
    """Tests for drift-report.schema.json."""

    def test_valid_drift_report_validates(self):
        """A well-formed drift-report artifact must validate."""
        validate(VALID_DRIFT_REPORT, "drift-report")

    def test_invalid_severity_rejected(self):
        """A severity value outside the enum must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["severity"] = "catastrophic"
        assert not is_valid(data, "drift-report")

    def test_empty_recommendations_rejected(self):
        """An empty recommendations array must be rejected (minItems: 1)."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["recommendations"] = []
        assert not is_valid(data, "drift-report")

    def test_invalid_classification_rejected(self):
        """A classification not in the fixed taxonomy must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["classification"] = "disk_full"
        assert not is_valid(data, "drift-report")

    def test_missing_required_field_classification(self):
        """Missing required field 'classification' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        del data["classification"]
        assert not is_valid(data, "drift-report")

    def test_missing_required_field_likely_cause(self):
        """Missing required field 'likely_cause' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        del data["likely_cause"]
        assert not is_valid(data, "drift-report")

    def test_missing_required_field_recommendations(self):
        """Missing required field 'recommendations' must be caught."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        del data["recommendations"]
        assert not is_valid(data, "drift-report")

    def test_recommendation_missing_action(self):
        """A recommendation missing 'action' must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        del data["recommendations"][0]["action"]
        assert not is_valid(data, "drift-report")

    def test_recommendation_invalid_confidence(self):
        """A recommendation with invalid confidence must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["recommendations"][0]["confidence"] = "very_high"
        assert not is_valid(data, "drift-report")

    def test_additional_properties_rejected(self):
        """Extra top-level properties must be rejected."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["extra_field"] = "should fail"
        assert not is_valid(data, "drift-report")

    def test_invalid_schema_version_rejected(self):
        """schema_version must be exactly 1."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["schema_version"] = 2
        assert not is_valid(data, "drift-report")

    def test_empty_likely_cause_rejected(self):
        """likely_cause must have minLength 1."""
        data = copy.deepcopy(VALID_DRIFT_REPORT)
        data["likely_cause"] = ""
        assert not is_valid(data, "drift-report")


# ---------------------------------------------------------------------------
# Baseline reference fixture test
# ---------------------------------------------------------------------------

class TestBaselineReferenceFixture:
    """The drift baseline reference fixture must validate against baseline.schema.json."""

    def test_drift_baseline_reference_validates(self):
        """testdata/drift_baseline_reference.json must be a valid baseline artifact."""
        data = _load_fixture("drift_baseline_reference.json")
        validate(data, "baseline")
