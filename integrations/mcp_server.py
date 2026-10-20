"""Optional, local stdio MCP access to SLOscope's deterministic evidence review.

No model, network, shell, deployment or file-store capability is exposed. Inputs
are inline artifacts supplied by the client; approval never authenticates their
origin or proves causal prose.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

# Direct execution from any cwd, without requiring SLOscope to be packaged first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from baseline import compute_baseline as _compute_baseline
from classify import (
    CONSISTENT_CLASSES,
    check_actuation,
    check_class_consistency,
    check_grounding,
    check_severity_consistency,
    normalized_report_class,
)
from consistency import check_consistency
from deviation import compute_drift_signal
from evidence_constraints import (
    EvidenceConstraintError,
    classification_constraints,
    finite_artifact,
    input_digest,
    proposal_claim_errors,
    proposal_constraints,
    require_coverage,
)
from schemas.validate import validate

MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
server = MCPServer(
    "sloscope-evidence-review",
    version="0.1.0",
    instructions=(
        "Review only caller-supplied evidence. Abstained means no supported verdict. "
        "Admissible means schema and numeric checks passed; it does not authenticate "
        "telemetry or verify causal explanations. Never execute proposed remediation."
    ),
)


def _bounded(*artifacts: dict[str, Any]) -> None:
    for artifact in artifacts:
        finite_artifact(artifact)
        if len(json.dumps(artifact, allow_nan=False).encode()) > MAX_ARTIFACT_BYTES:
            raise EvidenceConstraintError("Artifact exceeds the 2 MiB inline review limit")


def _abstain(error: Exception) -> dict[str, Any]:
    # JSON Schema's full str(error) repeats payload data. Keep the reason concise.
    reason = getattr(error, "message", str(error)).splitlines()[0]
    return {"status": "abstained", "reason": reason, "human_review_required": True}


@server.tool(annotations=ANNOTATIONS)
def compute_baseline(evidence: dict[str, Any]) -> dict[str, Any]:
    """Compute a baseline from inline telemetry; abstain on invalid/low-coverage input."""
    try:
        _bounded(evidence)
        result = _compute_baseline(evidence)
        require_coverage(result)
        return {
            "status": "measured",
            "baseline": result,
            "input_sha256": input_digest(evidence),
            "human_review_required": True,
        }
    except Exception as error:
        # Every invalid input abstains. No fallback or model call.
        return _abstain(error)


@server.tool(annotations=ANNOTATIONS)
def measure_drift(baseline: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Measure drift against a supplied reference without storing/replacing that reference."""
    try:
        _bounded(baseline, evidence)
        validate(baseline, "baseline")
        validate(evidence, "evidence")
        require_coverage(baseline)
        if (baseline["service"], baseline["namespace"]) != (evidence["service"], evidence["namespace"]):
            raise EvidenceConstraintError("Reference and live evidence identities differ")
        signal = compute_drift_signal({"baseline": baseline, "live_evidence": evidence})
        constraint = classification_constraints(signal)
        return {
            "status": "measured",
            "drift_signal": signal,
            "evidence_constraint": constraint,
            "reference_sha256": input_digest(baseline),
            "evidence_sha256": input_digest(evidence),
            "human_review_required": True,
        }
    except Exception as error:
        return _abstain(error)


@server.tool(annotations=ANNOTATIONS)
def review_classification(signal: dict[str, Any], report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return evidence-permitted classes, and optionally validate a supplied model report.

    This never calls a model. A permitted class is not proof of a causal explanation.
    """
    try:
        _bounded(signal, *([report] if report is not None else []))
        constraint = classification_constraints(signal)
        permitted = sorted(CONSISTENT_CLASSES.get(normalized_report_class(signal), set()))
        if not permitted:
            raise EvidenceConstraintError("No evidence-permitted classification")
        if report is not None:
            validate(report, "drift-report")
            errors = []
            if report["service"] != signal["service"]:
                errors.append("Report service does not match measured evidence")
            supplied_constraint = report.get("evidence_constraint")
            if supplied_constraint is not None and supplied_constraint.get("input_sha256") != constraint["input_sha256"]:
                errors.append("Report evidence digest does not match submitted signal")
            errors.extend(check_class_consistency(report, signal))
            errors.extend(check_severity_consistency(report, signal))
            errors.extend(check_grounding(report, signal))
            errors.extend(check_actuation(report))
            if errors:
                return {"status": "abstained", "errors": errors, "human_review_required": True}
        return {
            "status": "admissible",
            "permitted_classifications": permitted,
            "report_checked": report is not None,
            "evidence_constraint": constraint,
            "human_review_required": True,
        }
    except Exception as error:
        return _abstain(error)


@server.tool(annotations=ANNOTATIONS)
def review_proposal(baseline: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    """Check a supplied proposal's evidence, numeric citations and target constraints."""
    try:
        _bounded(baseline, proposal)
        validate(baseline, "baseline")
        validate(proposal, "proposal")
        errors = check_consistency(proposal, baseline)
        errors.extend(proposal_constraints(proposal, baseline))
        errors.extend(proposal_claim_errors(proposal, baseline))
        if errors:
            return {"status": "abstained", "errors": errors, "human_review_required": True}
        return {
            "status": "admissible",
            "baseline_sha256": input_digest(baseline),
            "proposal_sha256": input_digest(proposal),
            "prose_status": "advisory_not_verified_causality",
            "human_review_required": True,
        }
    except Exception as error:
        return _abstain(error)


if __name__ == "__main__":
    # Fixed stdio transport: no network listener, remote URL or auth configuration.
    server.run(transport="stdio")
