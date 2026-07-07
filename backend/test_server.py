"""Backend API test suite for sloscope."""

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "analysis"))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import server
from server import app

client = TestClient(app)


# --- CORS config ---

class TestCORSConfig:
    def test_default_cors_origins_are_not_wildcard(self, monkeypatch):
        monkeypatch.delenv("SLOSCOPE_ALLOW_ANY_ORIGIN", raising=False)
        monkeypatch.delenv("SLOSCOPE_CORS_ORIGINS", raising=False)
        assert server.get_cors_origins() != ["*"]

    def test_wildcard_cors_requires_explicit_opt_in(self, monkeypatch):
        monkeypatch.setenv("SLOSCOPE_ALLOW_ANY_ORIGIN", "true")
        monkeypatch.delenv("SLOSCOPE_CORS_ORIGINS", raising=False)
        assert server.get_cors_origins() == ["*"]

    def test_cors_origins_from_env(self, monkeypatch):
        monkeypatch.delenv("SLOSCOPE_ALLOW_ANY_ORIGIN", raising=False)
        monkeypatch.setenv(
            "SLOSCOPE_CORS_ORIGINS",
            "https://example.com, https://admin.example.com",
        )
        assert server.get_cors_origins() == [
            "https://example.com",
            "https://admin.example.com",
        ]


# --- Health ---

class TestHealth:
    def test_health_returns_ok(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_includes_version(self):
        r = client.get("/health")
        assert "version" in r.json()


# --- Evidence ---

class TestEvidence:
    def test_collect_evidence_default_service(self):
        r = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"})
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "checkout-api"
        assert data["namespace"] == "payments"
        assert "series" in data
        assert "provenance" in data

    def test_collect_evidence_patches_service_name(self):
        r = client.post("/api/v1/evidence", json={"service": "my-custom-svc", "namespace": "prod", "fixture": "checkout-api"})
        assert r.status_code == 200
        assert r.json()["service"] == "my-custom-svc"
        assert r.json()["namespace"] == "prod"

    def test_collect_evidence_unknown_fixture_returns_404(self):
        r = client.post("/api/v1/evidence", json={"service": "nonexistent-svc", "namespace": "x", "fixture": "nonexistent"})
        assert r.status_code == 404

    def test_evidence_has_histogram_data(self):
        r = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"})
        series = r.json()["series"]
        assert "latency_histogram" in series
        assert len(series["latency_histogram"]["buckets"]) > 0
        assert series["latency_histogram"]["total_count"] > 0

    def test_evidence_has_request_total(self):
        r = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"})
        assert r.json()["series"]["request_total"]["total"] > 0

    def test_evidence_has_error_total(self):
        r = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"})
        assert "error_total" in r.json()["series"]

    def test_evidence_has_provenance(self):
        r = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"})
        prov = r.json()["provenance"]
        assert "prometheus_endpoint" in prov
        assert "query_timestamps" in prov


# --- Baseline ---

class TestBaseline:
    def _get_evidence(self):
        return client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()

    def test_compute_baseline_succeeds(self):
        ev = self._get_evidence()
        r = client.post("/api/v1/baseline", json={"evidence": ev})
        assert r.status_code == 200

    def test_baseline_has_all_indicators(self):
        ev = self._get_evidence()
        r = client.post("/api/v1/baseline", json={"evidence": ev})
        indicators = r.json()["indicators"]
        assert "latency" in indicators
        assert "error_rate" in indicators
        assert "availability" in indicators
        assert "throughput" in indicators

    def test_baseline_latency_has_percentiles(self):
        ev = self._get_evidence()
        bl = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        lat = bl["indicators"]["latency"]
        for key in ["p50_ms", "p90_ms", "p95_ms", "p99_ms", "stddev_ms"]:
            assert key in lat
            assert lat[key] > 0

    def test_baseline_latency_order(self):
        ev = self._get_evidence()
        bl = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        lat = bl["indicators"]["latency"]
        assert lat["p50_ms"] <= lat["p90_ms"] <= lat["p95_ms"] <= lat["p99_ms"]

    def test_baseline_availability_in_range(self):
        ev = self._get_evidence()
        bl = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        avail = bl["indicators"]["availability"]["ratio"]
        assert 0 < avail <= 1

    def test_baseline_error_rate_in_range(self):
        ev = self._get_evidence()
        bl = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        err = bl["indicators"]["error_rate"]["ratio"]
        assert 0 <= err < 1

    def test_baseline_is_deterministic(self):
        ev = self._get_evidence()
        bl1 = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        bl2 = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        assert json.dumps(bl1, sort_keys=True) == json.dumps(bl2, sort_keys=True)

    def test_baseline_invalid_evidence_returns_400(self):
        r = client.post("/api/v1/baseline", json={"evidence": {"bad": "data"}})
        assert r.status_code == 400

    def test_baseline_has_provenance(self):
        ev = self._get_evidence()
        bl = client.post("/api/v1/baseline", json={"evidence": ev}).json()
        assert "provenance" in bl
        assert "coverage_ratio" in bl["provenance"]


# --- Propose ---

class TestPropose:
    def test_propose_falls_back_to_recorded(self):
        """Without LLM env vars, should return a recorded response."""
        # Clear LLM env vars if set
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            r = client.post("/api/v1/propose", json={"baseline": bl})
            assert r.status_code == 200
            data = r.json()
            assert data["schema_version"] == 3
            assert len(data["slos"]) >= 1
            for slo in data["slos"]:
                assert "target_op" in slo
                assert slo["target_op"] in ("lte", "gte")
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_propose_has_headroom(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            r = client.post("/api/v1/propose", json={"baseline": bl})
            for slo in r.json()["slos"]:
                if "headroom" in slo and slo["headroom"]:
                    assert "observed_value" in slo["headroom"]
                    assert "margin" in slo["headroom"]
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_propose_accepts_maturity_and_context(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            r = client.post("/api/v1/propose", json={"baseline": bl, "maturity": "mature", "context_type": "infra"})
            assert r.status_code == 200
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_live_propose_context_does_not_mutate_process_env(self, monkeypatch):
        import propose as propose_module

        captured = {}

        def fake_propose(baseline, client=None, model=None, maturity=None, context_type=None):
            captured["maturity"] = maturity
            captured["context_type"] = context_type
            return {
                "schema_version": 3,
                "service": baseline["service"],
                "baseline_schema_version": baseline["schema_version"],
                "slos": [],
            }

        monkeypatch.setattr(propose_module, "propose", fake_propose)
        monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("SLOSCOPE_MATURITY_TIER", "original-tier")
        monkeypatch.setenv("SLOSCOPE_CONTEXT_TYPE", "original-context")

        bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
        r = client.post(
            "/api/v1/propose",
            json={"baseline": bl, "maturity": "mature", "context_type": "infra"},
        )
        assert r.status_code == 200
        assert captured == {"maturity": "mature", "context_type": "infra"}
        assert os.environ["SLOSCOPE_MATURITY_TIER"] == "original-tier"
        assert os.environ["SLOSCOPE_CONTEXT_TYPE"] == "original-context"


# --- Drift Signal ---

class TestDriftSignal:
    def test_compute_drift_signal_succeeds(self):
        bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
        ev = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()
        r = client.post("/api/v1/drift/signal", json={"baseline": bl, "live_evidence": ev})
        assert r.status_code == 200

    def test_drift_signal_has_indicators(self):
        bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
        ev = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()
        r = client.post("/api/v1/drift/signal", json={"baseline": bl, "live_evidence": ev})
        data = r.json()
        assert "indicators" in data
        assert len(data["indicators"]) > 0
        assert "dominant_signal" in data
        assert "all_breached_indicators" in data

    def test_drift_signal_has_per_indicator_fields(self):
        bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
        ev = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()
        r = client.post("/api/v1/drift/signal", json={"baseline": bl, "live_evidence": ev})
        ind = r.json()["indicators"][0]
        for field in ["name", "live_value", "baseline_value", "abs_deviation", "direction", "band_breach", "first_pass_class"]:
            assert field in ind

    def test_drift_signal_is_deterministic(self):
        bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
        ev = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()
        r1 = client.post("/api/v1/drift/signal", json={"baseline": bl, "live_evidence": ev}).json()
        r2 = client.post("/api/v1/drift/signal", json={"baseline": bl, "live_evidence": ev}).json()
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)


# --- Drift Classify ---

class TestDriftClassify:
    def test_classify_falls_back_to_recorded(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            ds = client.get("/api/v1/fixtures/drift/latency_regression").json()
            r = client.post("/api/v1/drift/classify", json={"drift_signal": ds})
            assert r.status_code == 200
            data = r.json()
            assert data["classification"] == "latency_regression"
            assert data["severity"] in ("critical", "high", "medium", "low", "info")
            assert len(data["recommendations"]) >= 1
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_classify_no_drift_returns_info(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            ds = client.get("/api/v1/fixtures/drift/no_significant_drift").json()
            r = client.post("/api/v1/drift/classify", json={"drift_signal": ds})
            assert r.status_code == 200
            assert r.json()["classification"] == "no_significant_drift"
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_refined_dependency_class_falls_back_to_latency_report(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            ds = client.get("/api/v1/fixtures/drift/latency_regression").json()
            ds["dominant_signal"]["class"] = "dependency_latency_regression"
            r = client.post("/api/v1/drift/classify", json={"drift_signal": ds})
            assert r.status_code == 200
            assert r.json()["classification"] == "latency_regression"
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_refined_error_category_class_falls_back_to_error_rate_report(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            ds = client.get("/api/v1/fixtures/drift/error_rate_elevation").json()
            ds["dominant_signal"]["class"] = "error_category_shift"
            ds["indicators"][0]["first_pass_class"] = "error_category_shift"
            ds["indicators"][0]["band_breach"] = True
            r = client.post("/api/v1/drift/classify", json={"drift_signal": ds})
            assert r.status_code == 200
            assert r.json()["classification"] == "error_rate_elevation"
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_live_classify_context_does_not_mutate_process_env(self, monkeypatch):
        import classify as classify_module

        captured = {}

        def fake_classify(drift_signal, client=None, model=None, context_type=None):
            captured["context_type"] = context_type
            return {
                "schema_version": 1,
                "service": drift_signal["service"],
                "classification": "no_significant_drift",
                "severity": "info",
                "likely_cause": "No significant drift.",
                "recommendations": [
                    {
                        "action": "Continue monitoring",
                        "confidence": "high",
                        "rationale": "No indicators breached.",
                    }
                ],
            }

        monkeypatch.setattr(classify_module, "classify", fake_classify)
        monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("SLOSCOPE_CONTEXT_TYPE", "original-context")

        ds = client.get("/api/v1/fixtures/drift/no_significant_drift").json()
        r = client.post(
            "/api/v1/drift/classify",
            json={"drift_signal": ds, "context_type": "infra"},
        )
        assert r.status_code == 200
        assert captured == {"context_type": "infra"}
        assert os.environ["SLOSCOPE_CONTEXT_TYPE"] == "original-context"


# --- Render ---

class TestRender:
    def test_render_returns_openslo_and_prom_rules(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            pr = client.post("/api/v1/propose", json={"baseline": bl}).json()
            r = client.post("/api/v1/render", json={"proposal": pr, "service": "checkout-api"})
            assert r.status_code == 200
            data = r.json()
            assert "openslo_yaml" in data
            assert "prom_rules" in data
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_openslo_has_correct_ops(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            pr = client.post("/api/v1/propose", json={"baseline": bl}).json()
            r = client.post("/api/v1/render", json={"proposal": pr, "service": "checkout-api"})
            yaml_content = r.json()["openslo_yaml"]
            assert "op: lte" in yaml_content or "op: gte" in yaml_content
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_prom_rules_has_recording_rules(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            pr = client.post("/api/v1/propose", json={"baseline": bl}).json()
            r = client.post("/api/v1/render", json={"proposal": pr, "service": "checkout-api"})
            rules = r.json()["prom_rules"]
            assert "groups:" in rules
            assert "record:" in rules
            assert "slo:request_latency_p99:latency_ratio" in rules
            assert 'namespace="payments"' in rules
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_render_accepts_namespace(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
            pr = client.post("/api/v1/propose", json={"baseline": bl}).json()
            r = client.post(
                "/api/v1/render",
                json={"proposal": pr, "service": "checkout-api", "namespace": "staging"},
            )
            assert r.status_code == 200
            assert 'namespace="staging"' in r.json()["prom_rules"]
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_render_rejects_invalid_service_name(self):
        bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            pr = client.post("/api/v1/propose", json={"baseline": bl}).json()
            r = client.post(
                "/api/v1/render",
                json={"proposal": pr, "service": "bad_service"},
            )
            assert r.status_code == 400
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key


# --- Fixtures ---

class TestFixtures:
    def test_list_fixtures(self):
        r = client.get("/api/v1/fixtures")
        assert r.status_code == 200
        data = r.json()
        assert "services" in data
        assert "checkout-api" in data["services"]
        assert "drift_scenarios" in data
        assert "latency_regression" in data["drift_scenarios"]

    def test_get_baseline_fixture(self):
        r = client.get("/api/v1/fixtures/baseline/checkout-api")
        assert r.status_code == 200
        assert r.json()["service"] == "checkout-api"

    def test_get_baseline_fixture_not_found(self):
        r = client.get("/api/v1/fixtures/baseline/nonexistent")
        assert r.status_code == 404

    def test_get_drift_fixture(self):
        r = client.get("/api/v1/fixtures/drift/latency_regression")
        assert r.status_code == 200
        assert r.json()["dominant_signal"]["class"] == "latency_regression"

    def test_get_drift_fixture_not_found(self):
        r = client.get("/api/v1/fixtures/drift/nonexistent")
        assert r.status_code == 404

    def test_all_drift_scenarios_loadable(self):
        fixtures = client.get("/api/v1/fixtures").json()
        for scenario in fixtures["drift_scenarios"]:
            r = client.get(f"/api/v1/fixtures/drift/{scenario}")
            assert r.status_code == 200, f"Failed to load drift scenario: {scenario}"

    def test_all_baseline_services_loadable(self):
        fixtures = client.get("/api/v1/fixtures").json()
        for service in fixtures["services"]:
            r = client.get(f"/api/v1/fixtures/baseline/{service}")
            assert r.status_code == 200, f"Failed to load baseline for: {service}"


# --- Full Pipeline ---

class TestFullPipeline:
    """End-to-end pipeline test through all API stages."""

    def test_evidence_to_baseline_to_propose(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            # Stage 1: Evidence
            ev = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()
            assert "series" in ev

            # Stage 2: Baseline (deterministic)
            bl = client.post("/api/v1/baseline", json={"evidence": ev}).json()
            assert bl["indicators"]["latency"]["p99_ms"] > 0

            # Stage 3: Proposal (recorded fallback)
            pr = client.post("/api/v1/propose", json={"baseline": bl}).json()
            assert len(pr["slos"]) >= 1
            assert all("target_op" in s for s in pr["slos"])

            # Stage 4: Render
            rendered = client.post("/api/v1/render", json={"proposal": pr, "service": "checkout-api"}).json()
            assert "openslo_yaml" in rendered
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key

    def test_baseline_to_drift_to_classify(self):
        old_base = os.environ.pop("LLM_BASE_URL", None)
        old_key = os.environ.pop("LLM_API_KEY", None)
        try:
            # Load baseline fixture
            bl = client.get("/api/v1/fixtures/baseline/checkout-api").json()

            # Load live evidence
            ev = client.post("/api/v1/evidence", json={"service": "checkout-api", "namespace": "payments"}).json()

            # Compute drift (deterministic)
            ds = client.post("/api/v1/drift/signal", json={"baseline": bl, "live_evidence": ev}).json()
            assert "dominant_signal" in ds

            # Classify (recorded fallback)
            dr = client.post("/api/v1/drift/classify", json={"drift_signal": ds}).json()
            assert "classification" in dr
            assert "recommendations" in dr
        finally:
            if old_base: os.environ["LLM_BASE_URL"] = old_base
            if old_key: os.environ["LLM_API_KEY"] = old_key
