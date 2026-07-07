#!/usr/bin/env python3
"""sloscope API server for the presentation/demo/lab frontend."""

import json
import os
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

# Add analysis directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
TESTDATA_DIR = PROJECT_ROOT / "testdata"
FIXTURES_DIR = ANALYSIS_DIR / "evals" / "fixtures"
RECORDED_DIR = ANALYSIS_DIR / "evals" / "recorded"
DRIFT_FIXTURES_DIR = FIXTURES_DIR / "drift"
DRIFT_RECORDED_DIR = RECORDED_DIR / "drift"

sys.path.insert(0, str(ANALYSIS_DIR))

from baseline import compute_baseline
from schemas.validate import validate, is_valid
from serialize import serialize

tags_metadata = [
    {"name": "System", "description": "Health and status"},
    {"name": "SLO Generation", "description": "Evidence collection, baseline computation, SLO proposal, artifact rendering"},
    {"name": "Drift Detection", "description": "Drift signal computation and classification with remediation"},
    {"name": "Fixtures", "description": "Pre-built sample data for demo and testing"},
    {"name": "Dashboard", "description": "Multi-service dashboard APIs backed by the artifact store"},
]

app = FastAPI(
    title="sloscope API",
    version="0.1.0",
    description="Evidence-based SLO/SLI generator and drift detector. Two-stage architecture: deterministic baseline from telemetry, then LLM-powered proposals and drift classification.",
    openapi_tags=tags_metadata,
)


def get_cors_origins():
    """Resolve CORS origins from environment with explicit wildcard opt-in."""
    allow_any = os.environ.get("SLOSCOPE_ALLOW_ANY_ORIGIN", "").lower()
    if allow_any in ("1", "true", "yes"):
        return ["*"]

    raw = os.environ.get("SLOSCOPE_CORS_ORIGINS", "")
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if origins:
            return origins

    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---

class EvidenceRequest(BaseModel):
    service: str = "checkout-api"
    namespace: str = "payments"
    fixture: Optional[str] = None

class BaselineRequest(BaseModel):
    evidence: dict

class ProposeRequest(BaseModel):
    baseline: dict
    maturity: str = "growing"
    context_type: str = "service"

class DriftSignalRequest(BaseModel):
    baseline: dict
    live_evidence: dict

class DriftClassifyRequest(BaseModel):
    drift_signal: dict
    context_type: str = "service"

class RenderRequest(BaseModel):
    proposal: dict
    service: str = "checkout-api"
    namespace: str = "payments"


# --- Fixture loading ---

EVIDENCE_FIXTURES = {
    "checkout-api": TESTDATA_DIR / "evidence_checkout_api.json",
    "empty": TESTDATA_DIR / "evidence_empty.json",
}

BASELINE_FIXTURES = {
    "checkout-api": FIXTURES_DIR / "web_api_baseline.json",
    "api-gateway": FIXTURES_DIR / "high_traffic_baseline.json",
    "batch-processor": FIXTURES_DIR / "batch_processor_baseline.json",
}

DRIFT_EVIDENCE_FIXTURES = {
    "latency-regression": TESTDATA_DIR / "drift_live_latency_regression.json",
    "no-drift": TESTDATA_DIR / "drift_live_no_drift.json",
}


def load_fixture(path):
    with open(path) as f:
        return json.load(f)


# --- Endpoints ---

@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/v1/evidence", tags=["SLO Generation"], summary="Collect evidence")
def collect_evidence(req: EvidenceRequest):
    """Load demo fixture evidence and patch service/namespace for the request."""
    fixture_key = req.fixture or req.service
    fixture_path = EVIDENCE_FIXTURES.get(fixture_key)
    if not fixture_path or not fixture_path.exists():
        raise HTTPException(404, f"No evidence fixture for '{fixture_key}'. Available: {list(EVIDENCE_FIXTURES.keys())}")

    evidence = load_fixture(fixture_path)
    # Patch service/namespace to match request
    evidence["service"] = req.service
    evidence["namespace"] = req.namespace
    return evidence


@app.post("/api/v1/baseline", tags=["SLO Generation"], summary="Compute baseline")
def compute_baseline_endpoint(req: BaselineRequest):
    """Compute a deterministic empirical baseline from evidence."""
    try:
        result = compute_baseline(req.evidence)
        return result
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/propose", tags=["SLO Generation"], summary="Propose SLOs")
def propose_slos(req: ProposeRequest):
    """Generate SLO/SLA proposals grounded in the baseline. Falls back to recorded responses when LLM is not configured."""
    # Check if LLM is configured
    llm_base = os.environ.get("LLM_BASE_URL", "")
    llm_key = os.environ.get("LLM_API_KEY", "")

    if not llm_base or not llm_key:
        # Fall back to recorded response
        service = req.baseline.get("service", "checkout-api")
        recorded_map = {
            "checkout-api": RECORDED_DIR / "web_api_baseline_response.json",
            "api-gateway": RECORDED_DIR / "high_traffic_baseline_response.json",
            "batch-processor": RECORDED_DIR / "batch_processor_baseline_response.json",
        }
        path = recorded_map.get(service)
        if path and path.exists():
            return load_fixture(path)
        raise HTTPException(503, "LLM not configured and no recorded response available")

    try:
        from propose import propose
        result = propose(
            req.baseline,
            maturity=req.maturity,
            context_type=req.context_type,
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Proposal failed: {e}")


@app.post("/api/v1/drift/signal", tags=["Drift Detection"], summary="Compute drift signal")
def compute_drift_signal_endpoint(req: DriftSignalRequest):
    """Compute deterministic deviation between baseline and live evidence."""
    try:
        from deviation import compute_drift_signal
        combined = {
            "live_evidence": req.live_evidence,
            "baseline": req.baseline,
        }
        result = compute_drift_signal(combined)
        return result
    except Exception as e:
        raise HTTPException(400, f"Drift signal computation failed: {e}")


@app.post("/api/v1/drift/classify", tags=["Drift Detection"], summary="Classify drift")
def classify_drift(req: DriftClassifyRequest):
    """Classify drift and generate remediation recommendations. Falls back to recorded responses when LLM is not configured."""
    llm_base = os.environ.get("LLM_BASE_URL", "")
    llm_key = os.environ.get("LLM_API_KEY", "")

    if not llm_base or not llm_key:
        # Fall back to recorded response based on dominant signal class
        from classify import normalized_report_class
        dominant_class = normalized_report_class(req.drift_signal) or "no_significant_drift"
        recorded_path = DRIFT_RECORDED_DIR / f"{dominant_class}_response.json"
        if recorded_path.exists():
            return load_fixture(recorded_path)
        raise HTTPException(503, "LLM not configured and no recorded response available")

    try:
        from classify import classify
        result = classify(req.drift_signal, context_type=req.context_type)
        return result
    except Exception as e:
        raise HTTPException(500, f"Classification failed: {e}")


@app.post("/api/v1/render", tags=["SLO Generation"], summary="Render artifacts")
def render_artifacts(req: RenderRequest):
    """Render OpenSLO YAML, Prometheus rules, and audit bundle from a proposal."""
    proposal = req.proposal
    service = req.service
    namespace = req.namespace

    # Simple Python-side rendering for the demo
    openslo = render_openslo(proposal)
    prom_rules = render_prom_rules(proposal, service, namespace)

    return {
        "openslo_yaml": openslo,
        "prom_rules": prom_rules,
    }


def render_openslo(proposal):
    """Lightweight Python-side OpenSLO rendering."""
    lines = []
    for i, slo in enumerate(proposal.get("slos", [])):
        if i > 0:
            lines.append("---")
        service = proposal.get("service", "unknown")
        name = slo.get("sli_name", "unnamed").lower().replace(" ", "-").replace("_", "-")
        target_op = slo.get("target_op", "lte")

        lines.append("apiVersion: openslo/v1")
        lines.append("kind: SLO")
        lines.append("metadata:")
        lines.append(f"  name: {service}-{name}")
        lines.append(f"  displayName: {slo.get('sli_name', '')}")
        lines.append("spec:")
        lines.append(f"  service: {service}")
        lines.append(f"  description: {slo.get('sli_definition', '')}")
        lines.append("  budgetingMethod: Occurrences")
        lines.append("  objectives:")
        lines.append(f"    - displayName: {slo.get('sli_name', '')}")
        lines.append(f"      target: {slo.get('slo_target', slo.get('target', 0))}")
        lines.append(f"      op: {target_op}")

    return "\n".join(lines)


K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
METRIC_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9_]")
UNDERSCORE_RE = re.compile(r"_+")


def validate_k8s_name(field, value):
    if not value or len(value) > 63 or not K8S_NAME_RE.match(value):
        raise HTTPException(400, f"{field} must be a Kubernetes DNS label")


def prom_label_value(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def prom_regex_literal(value):
    return prom_label_value(re.escape(value))


def prom_metric_segment(value):
    value = value.lower().replace("-", "_").replace(" ", "_")
    value = METRIC_SEGMENT_RE.sub("_", value)
    value = UNDERSCORE_RE.sub("_", value).strip("_")
    if not value:
        return "unnamed"
    if value[0].isdigit():
        value = "_" + value
    return value


def render_prom_rules(proposal, service, namespace="payments"):
    """Lightweight Python-side Prometheus rules rendering."""
    validate_k8s_name("service", service)
    validate_k8s_name("namespace", namespace)

    service_label = prom_label_value(service)
    namespace_label = prom_label_value(namespace)
    selector = f'service="{service_label}",namespace="{namespace_label}"'
    label_selector = f'{{service="{service_label}",namespace="{namespace_label}"}}'

    lines = ["groups:"]
    lines.append(f"  - name: {prom_metric_segment(service)}_slo_recording")
    lines.append("    rules:")

    for slo in proposal.get("slos", []):
        name = prom_metric_segment(slo.get("sli_name", "unnamed"))
        sli_type = slo.get("sli_type", "")

        if sli_type in ("availability", "error_rate"):
            lines.append(f"      - record: slo:{name}:error_ratio")
            lines.append("        expr: |")
            lines.append(f"          sum(rate(http_requests_total{{{selector},code=~\"5..\"}}[5m]))")
            lines.append("          /")
            lines.append(f"          sum(rate(http_requests_total{{{selector}}}[5m]))")
            lines.append("        labels:")
            lines.append(f"          service: {service}")
            lines.append(f"          namespace: {namespace}")
            lines.append(f"          slo: {name}")
        elif sli_type == "latency":
            target_sec = slo.get("sla_target", slo.get("target", 0)) / 1000
            lines.append(f"      - record: slo:{name}:latency_ratio")
            lines.append("        expr: |")
            lines.append(f"          sum(rate(http_request_duration_seconds_bucket{{{selector},le=\"{target_sec}\"}}[5m]))")
            lines.append("          /")
            lines.append(f"          sum(rate(http_request_duration_seconds_count{{{selector}}}[5m]))")
            lines.append("        labels:")
            lines.append(f"          service: {service}")
            lines.append(f"          namespace: {namespace}")
            lines.append(f"          slo: {name}")

    lines.append("")
    lines.append(f"  - name: {prom_metric_segment(service)}_slo_alerts")
    lines.append("    rules:")

    for slo in proposal.get("slos", []):
        name = prom_metric_segment(slo.get("sli_name", "unnamed"))
        error_budget = slo.get("error_budget_percent", 0) / 100
        for window in slo.get("burn_rate_policy", {}).get("windows", []):
            severity = window.get("severity", "warning")
            long_window = window.get("long_window", "1h")
            short_window = window.get("short_window", "5m")
            burn_rate = window.get("burn_rate", 1)
            alert_name = "".join(
                part.capitalize()
                for part in re.split(r"[^a-zA-Z0-9]+", slo.get("sli_name", "slo"))
                if part
            )
            lines.append(f"      - alert: SLO{alert_name}BurnRate{severity.capitalize()}")
            lines.append("        expr: |")
            if slo.get("sli_type") in ("availability", "error_rate"):
                lines.append(f"          avg_over_time(slo:{name}:error_ratio{label_selector}[{long_window}]) > {burn_rate} * {error_budget}")
                lines.append("          and")
                lines.append(f"          avg_over_time(slo:{name}:error_ratio{label_selector}[{short_window}]) > {burn_rate} * {error_budget}")
            elif slo.get("sli_type") == "latency":
                target_sec = slo.get("sla_target", slo.get("target", 0)) / 1000
                lines.append("          (")
                lines.append(f"            1 - (sum(rate(http_request_duration_seconds_bucket{{{selector},le=\"{target_sec}\"}}[{long_window}])) / sum(rate(http_request_duration_seconds_count{{{selector}}}[{long_window}])))")
                lines.append(f"          ) > {burn_rate} * {error_budget}")
                lines.append("          and")
                lines.append("          (")
                lines.append(f"            1 - (sum(rate(http_request_duration_seconds_bucket{{{selector},le=\"{target_sec}\"}}[{short_window}])) / sum(rate(http_request_duration_seconds_count{{{selector}}}[{short_window}])))")
                lines.append(f"          ) > {burn_rate} * {error_budget}")
            else:
                continue
            lines.append("        labels:")
            lines.append(f"          severity: {severity}")
            lines.append(f"          service: {service}")
            lines.append(f"          namespace: {namespace}")
            lines.append(f"          slo: {name}")

    return "\n".join(lines)


# --- Available fixtures listing ---

@app.get("/api/v1/fixtures", tags=["Fixtures"], summary="List fixtures")
def list_fixtures():
    """List available sample services and drift scenarios."""
    drift_scenarios = []
    if DRIFT_FIXTURES_DIR.exists():
        for f in sorted(DRIFT_FIXTURES_DIR.glob("*.json")):
            if f.name != "ground_truth.json":
                drift_scenarios.append(f.stem)

    return {
        "services": list(BASELINE_FIXTURES.keys()),
        "drift_scenarios": drift_scenarios,
    }


@app.get("/api/v1/fixtures/drift/{scenario}", tags=["Fixtures"], summary="Get drift fixture")
def get_drift_fixture(scenario: str):
    """Load a specific drift scenario fixture."""
    path = DRIFT_FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        raise HTTPException(404, f"Drift scenario '{scenario}' not found")
    return load_fixture(path)


@app.get("/api/v1/fixtures/baseline/{service}", tags=["Fixtures"], summary="Get baseline fixture")
def get_baseline_fixture(service: str):
    """Load a pre-computed baseline fixture for a sample service."""
    path = BASELINE_FIXTURES.get(service)
    if not path or not path.exists():
        raise HTTPException(404, f"Baseline fixture for '{service}' not found")
    return load_fixture(path)


# --- Artifact store + v2 dashboard API ---

from store import ArtifactStore

store = ArtifactStore()

# Seed demo data on startup if store is empty
if not store.list_services():
    from store import seed_demo_data
    seed_demo_data(store)


@app.get("/api/v2/summary", tags=["Dashboard"], summary="Aggregate status")
def get_summary():
    """Cross-service summary: total, healthy, degraded, critical counts."""
    return store.get_summary()


@app.get("/api/v2/services", tags=["Dashboard"], summary="List services")
def list_services():
    """All tracked services with current status."""
    return store.get_summary()["services"]


@app.get("/api/v2/services/{service}/baseline", tags=["Dashboard"], summary="Service baseline")
def get_service_baseline(service: str):
    """Most recent baseline for a service."""
    data = store.load(service, "baseline")
    if not data:
        raise HTTPException(404, f"No baseline for '{service}'")
    return data


@app.get("/api/v2/services/{service}/proposal", tags=["Dashboard"], summary="Service proposal")
def get_service_proposal(service: str):
    """Active SLO/SLA proposal for a service."""
    data = store.load(service, "proposal")
    if not data:
        raise HTTPException(404, f"No proposal for '{service}'")
    return data


@app.get("/api/v2/services/{service}/drift", tags=["Dashboard"], summary="Latest drift signal")
def get_service_drift(service: str):
    """Most recent drift signal for a service."""
    data = store.load(service, "drift-signal")
    if not data:
        raise HTTPException(404, f"No drift signal for '{service}'")
    return data


@app.get("/api/v2/services/{service}/drift/report", tags=["Dashboard"], summary="Latest drift report")
def get_service_drift_report(service: str):
    """Most recent drift classification and remediation."""
    data = store.load(service, "drift-report")
    if not data:
        raise HTTPException(404, f"No drift report for '{service}'")
    return data


@app.get("/api/v2/services/{service}/drift/history", tags=["Dashboard"], summary="Drift history")
def get_service_drift_history(service: str, limit: int = 10):
    """Historical drift signals, most recent first."""
    return store.load_history(service, "drift-signal", limit)


@app.get("/api/v2/services/{service}/budget", tags=["Dashboard"], summary="Error budget status")
def get_service_budget(service: str):
    """Error budget status per SLO."""
    data = store.get_error_budget(service)
    if not data:
        raise HTTPException(404, f"No proposal for '{service}'")
    return data


@app.get("/api/v2/services/{service}/recommendations", tags=["Dashboard"], summary="Open recommendations")
def get_service_recommendations(service: str):
    """Active remediation recommendations from the latest drift report."""
    return store.get_recommendations(service)


# --- Static file serving (production: serve built frontend) ---

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
