"""Tests for the file-based artifact store."""

import json
import tempfile
import pytest
from store import ArtifactStore


@pytest.fixture
def store(tmp_path):
    return ArtifactStore(str(tmp_path))


class TestArtifactStore:
    def test_save_and_load(self, store):
        store.save("test-svc", "baseline", {"service": "test-svc", "value": 42})
        data = store.load("test-svc", "baseline")
        assert data["service"] == "test-svc"
        assert data["value"] == 42

    def test_load_missing_returns_none(self, store):
        assert store.load("nonexistent", "baseline") is None

    def test_list_services(self, store):
        store.save("svc-a", "baseline", {"service": "svc-a"})
        store.save("svc-b", "baseline", {"service": "svc-b"})
        assert store.list_services() == ["svc-a", "svc-b"]

    def test_list_services_empty(self, store):
        assert store.list_services() == []

    def test_save_creates_history(self, store):
        store.save("test-svc", "baseline", {"v": 1})
        store.save("test-svc", "baseline", {"v": 2})
        history = store.load_history("test-svc", "baseline")
        assert len(history) == 2
        assert history[0]["v"] == 2  # most recent first

    def test_get_service_status_healthy(self, store):
        store.save("svc", "baseline", {"generated_at": "2026-01-01", "maturity_tier": "growing"})
        store.save("svc", "drift-signal", {
            "all_breached_indicators": [],
            "dominant_signal": {"class": "no_significant_drift"},
            "evaluated_at": "2026-01-02"
        })
        status = store.get_service_status("svc")
        assert status["status"] == "healthy"

    def test_get_service_status_degraded(self, store):
        store.save("svc", "baseline", {"generated_at": "2026-01-01"})
        store.save("svc", "drift-signal", {
            "all_breached_indicators": ["latency_p99"],
            "dominant_signal": {"class": "latency_regression"},
            "evaluated_at": "2026-01-02"
        })
        store.save("svc", "drift-report", {"severity": "medium"})
        status = store.get_service_status("svc")
        assert status["status"] == "degraded"

    def test_get_summary(self, store):
        store.save("svc-a", "baseline", {"generated_at": "2026-01-01"})
        store.save("svc-b", "baseline", {"generated_at": "2026-01-01"})
        summary = store.get_summary()
        assert summary["total_services"] == 2

    def test_get_error_budget(self, store):
        store.save("svc", "proposal", {
            "slos": [{"sli_name": "latency", "sli_type": "latency", "target_op": "lte",
                       "slo_target": 450, "sla_target": 595, "error_budget_percent": 0.5}]
        })
        budget = store.get_error_budget("svc")
        assert len(budget["budgets"]) == 1
        assert budget["budgets"][0]["status"] == "healthy"

    def test_get_recommendations_empty(self, store):
        assert store.get_recommendations("nonexistent") == []
