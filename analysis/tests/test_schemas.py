"""Contract tests for frozen JSON schemas."""

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
# Evidence schema tests
# ---------------------------------------------------------------------------

class TestEvidenceSchema:
    """Tests for evidence.schema.json."""

    def test_checkout_api_fixture_validates(self):
        data = _load_fixture("evidence_checkout_api.json")
        validate(data, "evidence")

    def test_empty_fixture_validates(self):
        data = _load_fixture("evidence_empty.json")
        validate(data, "evidence")

    def test_missing_required_field_service(self):
        data = _load_fixture("evidence_checkout_api.json")
        del data["service"]
        assert not is_valid(data, "evidence")

    def test_invalid_schema_version(self):
        data = _load_fixture("evidence_checkout_api.json")
        data["schema_version"] = 2
        assert not is_valid(data, "evidence")

    def test_invalid_coverage_ratio_above_one(self):
        data = _load_fixture("evidence_checkout_api.json")
        data["coverage_ratio"] = 1.5
        assert not is_valid(data, "evidence")

    def test_invalid_lookback_window_format(self):
        data = _load_fixture("evidence_checkout_api.json")
        data["lookback_window"] = "30 days"
        assert not is_valid(data, "evidence")

    def test_additional_properties_rejected(self):
        data = _load_fixture("evidence_checkout_api.json")
        data["extra_field"] = "should fail"
        assert not is_valid(data, "evidence")


# ---------------------------------------------------------------------------
# Baseline schema tests
# ---------------------------------------------------------------------------

class TestBaselineSchema:
    """Tests for baseline.schema.json."""

    VALID_BASELINE = {
        "schema_version": 1,
        "service": "checkout-api",
        "namespace": "payments",
        "lookback_window": "30d",
        "generated_at": "2026-07-05T12:30:00Z",
        "indicators": {
            "latency": {
                "p50_ms": 125.0,
                "p90_ms": 420.0,
                "p95_ms": 650.0,
                "p99_ms": 2100.0,
                "stddev_ms": 310.5,
                "sample_count": 100000,
                "source_query": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{service=\"checkout-api\"}[5m])) by (le))"
            },
            "error_rate": {
                "ratio": 0.0023,
                "stddev": 0.0005,
                "error_count": 230,
                "total_count": 100000,
                "source_query": "sum(increase(http_requests_errors_total{service=\"checkout-api\"}[30d])) / sum(increase(http_requests_total{service=\"checkout-api\"}[30d]))"
            },
            "availability": {
                "ratio": 0.9977,
                "definition": "1 - error_rate"
            },
            "throughput": {
                "mean_rps": 3.34,
                "p95_rps": 4.2,
                "stddev_rps": 0.42,
                "sample_count": 30
            },
            "saturation": {
                "cpu_mean_ratio": 0.401,
                "cpu_p95_ratio": 0.72,
                "memory_mean_ratio": 0.631,
                "memory_p95_ratio": 0.78,
                "available": True
            }
        },
        "provenance": {
            "prometheus_endpoint": "https://thanos-querier.openshift-monitoring.svc:9091",
            "query_timestamps": {
                "start": "2026-06-05T12:00:00Z",
                "end": "2026-07-05T12:00:00Z"
            },
            "coverage_ratio": 0.97
        }
    }

    def test_valid_baseline_validates(self):
        validate(self.VALID_BASELINE, "baseline")

    def test_missing_indicators(self):
        data = copy.deepcopy(self.VALID_BASELINE)
        del data["indicators"]
        assert not is_valid(data, "baseline")

    def test_missing_latency_in_indicators(self):
        data = copy.deepcopy(self.VALID_BASELINE)
        del data["indicators"]["latency"]
        assert not is_valid(data, "baseline")

    def test_error_rate_ratio_above_one(self):
        data = copy.deepcopy(self.VALID_BASELINE)
        data["indicators"]["error_rate"]["ratio"] = 1.5
        assert not is_valid(data, "baseline")

    def test_invalid_schema_version(self):
        data = copy.deepcopy(self.VALID_BASELINE)
        data["schema_version"] = 2
        assert not is_valid(data, "baseline")


# ---------------------------------------------------------------------------
# Proposal schema tests
# ---------------------------------------------------------------------------

class TestProposalSchema:
    """Tests for proposal.schema.json."""

    VALID_PROPOSAL = {
        "schema_version": 2,
        "service": "checkout-api",
        "baseline_schema_version": 1,
        "maturity_tier": "growing",
        "slos": [
            {
                "sli_name": "request_latency_p99",
                "sli_type": "latency",
                "sli_definition": "99th percentile latency of HTTP requests to checkout-api",
                "target": 2500.0,
                "target_op": "lte",
                "target_unit": "ms",
                "error_budget_percent": 0.1,
                "burn_rate_policy": {
                    "windows": [
                        {
                            "long_window": "1h",
                            "short_window": "5m",
                            "burn_rate": 14.4,
                            "severity": "critical"
                        },
                        {
                            "long_window": "6h",
                            "short_window": "30m",
                            "burn_rate": 6.0,
                            "severity": "warning"
                        }
                    ]
                },
                "rationale": "Based on 30-day baseline p99 of 2100ms with headroom for variance. Aligns with checkout flow user-facing latency expectations."
            },
            {
                "sli_name": "availability",
                "sli_type": "availability",
                "sli_definition": "Ratio of non-5xx responses to total requests",
                "target": 0.997,
                "target_op": "gte",
                "error_budget_percent": 0.3,
                "burn_rate_policy": {
                    "windows": [
                        {
                            "long_window": "1h",
                            "short_window": "5m",
                            "burn_rate": 14.4,
                            "severity": "critical"
                        }
                    ]
                },
                "rationale": "Baseline availability is 99.77%. Setting target at 99.7% to allow margin for deployments."
            }
        ]
    }

    def test_valid_proposal_validates(self):
        validate(self.VALID_PROPOSAL, "proposal")

    def test_empty_slos_array_rejected(self):
        data = copy.deepcopy(self.VALID_PROPOSAL)
        data["slos"] = []
        assert not is_valid(data, "proposal")

    def test_invalid_sli_type(self):
        data = copy.deepcopy(self.VALID_PROPOSAL)
        data["slos"][0]["sli_type"] = "unknown_type"
        assert not is_valid(data, "proposal")

    def test_missing_rationale(self):
        data = copy.deepcopy(self.VALID_PROPOSAL)
        del data["slos"][0]["rationale"]
        assert not is_valid(data, "proposal")

    def test_missing_burn_rate_windows(self):
        data = copy.deepcopy(self.VALID_PROPOSAL)
        data["slos"][0]["burn_rate_policy"]["windows"] = []
        assert not is_valid(data, "proposal")

    def test_invalid_schema_version(self):
        data = copy.deepcopy(self.VALID_PROPOSAL)
        data["schema_version"] = 1
        assert not is_valid(data, "proposal")
