#!/usr/bin/env python3
"""sloscope API server for the presentation/demo/lab frontend."""

import json
import os
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

app = FastAPI(title="sloscope API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

class RenderRequest(BaseModel):
    proposal: dict
    service: str = "checkout-api"


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

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.post("/api/v1/evidence")
def collect_evidence(req: EvidenceRequest):
    fixture_key = req.fixture or req.service
    fixture_path = EVIDENCE_FIXTURES.get(fixture_key)
    if not fixture_path or not fixture_path.exists():
        raise HTTPException(404, f"No evidence fixture for '{fixture_key}'. Available: {list(EVIDENCE_FIXTURES.keys())}")

    evidence = load_fixture(fixture_path)
    # Patch service/namespace to match request
    evidence["service"] = req.service
    evidence["namespace"] = req.namespace
    return evidence


@app.post("/api/v1/baseline")
def compute_baseline_endpoint(req: BaselineRequest):
    try:
        result = compute_baseline(req.evidence)
        return result
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/propose")
def propose_slos(req: ProposeRequest):
    # Set environment variables for the LLM stage
    os.environ["SLOSCOPE_MATURITY_TIER"] = req.maturity
    os.environ["SLOSCOPE_CONTEXT_TYPE"] = req.context_type

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
        result = propose(req.baseline)
        return result
    except Exception as e:
        raise HTTPException(500, f"Proposal failed: {e}")


@app.post("/api/v1/drift/signal")
def compute_drift_signal_endpoint(req: DriftSignalRequest):
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


@app.post("/api/v1/drift/classify")
def classify_drift(req: DriftClassifyRequest):
    llm_base = os.environ.get("LLM_BASE_URL", "")
    llm_key = os.environ.get("LLM_API_KEY", "")

    if not llm_base or not llm_key:
        # Fall back to recorded response based on dominant signal class
        dominant_class = req.drift_signal.get("dominant_signal", {}).get("class", "no_significant_drift")
        recorded_path = DRIFT_RECORDED_DIR / f"{dominant_class}_response.json"
        if recorded_path.exists():
            return load_fixture(recorded_path)
        raise HTTPException(503, "LLM not configured and no recorded response available")

    try:
        from classify import classify
        result = classify(req.drift_signal)
        return result
    except Exception as e:
        raise HTTPException(500, f"Classification failed: {e}")


@app.post("/api/v1/render")
def render_artifacts(req: RenderRequest):
    """Render OpenSLO YAML, Prometheus rules, and audit bundle from a proposal."""
    proposal = req.proposal
    service = req.service

    # Simple Python-side rendering for the demo
    openslo = render_openslo(proposal)
    prom_rules = render_prom_rules(proposal, service)

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
        lines.append(f"      target: {slo.get('target', 0)}")
        lines.append(f"      op: {target_op}")

    return "\n".join(lines)


def render_prom_rules(proposal, service):
    """Lightweight Python-side Prometheus rules rendering."""
    lines = ["groups:"]
    lines.append(f"  - name: {service}_slo_recording")
    lines.append("    rules:")

    for slo in proposal.get("slos", []):
        name = slo.get("sli_name", "unnamed").lower().replace(" ", "-").replace("_", "-")
        sli_type = slo.get("sli_type", "")

        if sli_type in ("availability", "error_rate"):
            lines.append(f"      - record: slo:{name}:error_ratio")
            lines.append("        expr: |")
            lines.append(f'          sum(rate(http_requests_total{{service="{service}",code=~"5.."}}[5m]))')
            lines.append("          /")
            lines.append(f'          sum(rate(http_requests_total{{service="{service}"}}[5m]))')
        elif sli_type == "latency":
            target_sec = slo.get("target", 0) / 1000
            lines.append(f"      - record: slo:{name}:latency_ratio")
            lines.append("        expr: |")
            lines.append(f'          sum(rate(http_request_duration_seconds_bucket{{service="{service}",le="{target_sec}"}}[5m]))')
            lines.append("          /")
            lines.append(f'          sum(rate(http_request_duration_seconds_count{{service="{service}"}}[5m]))')

    return "\n".join(lines)


# --- Available fixtures listing ---

@app.get("/api/v1/fixtures")
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


@app.get("/api/v1/fixtures/drift/{scenario}")
def get_drift_fixture(scenario: str):
    """Load a specific drift scenario fixture."""
    path = DRIFT_FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        raise HTTPException(404, f"Drift scenario '{scenario}' not found")
    return load_fixture(path)


@app.get("/api/v1/fixtures/baseline/{service}")
def get_baseline_fixture(service: str):
    """Load a pre-computed baseline fixture for a sample service."""
    path = BASELINE_FIXTURES.get(service)
    if not path or not path.exists():
        raise HTTPException(404, f"Baseline fixture for '{service}' not found")
    return load_fixture(path)


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
