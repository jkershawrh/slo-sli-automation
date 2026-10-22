"""Protocol-level tests: launch the optional server as an outside MCP host."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys

import pytest

pytest.importorskip("mcp", reason="Install requirements-mcp.txt for optional protocol tests")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT


def fixture(path):
    return json.loads((FIXTURE_ROOT / path).read_text())


@pytest.mark.asyncio
async def test_stdio_discovery_review_and_abstention(tmp_path):
    env = dict(os.environ)
    # A configured remote endpoint must not be needed or contacted by any tool.
    env.update(LLM_BASE_URL="http://127.0.0.1:9/v1", LLM_API_KEY="must-not-be-used", LLM_MODEL="must-not-be-called")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "integrations/mcp_server.py")],
        env=env,
        cwd=str(tmp_path),
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=10) as session:
            initialized = await session.initialize()
            assert initialized.server_info.name == "sloscope-evidence-review"
            tools = (await session.list_tools()).tools
            assert {tool.name for tool in tools} == {
                "compute_baseline", "measure_drift", "review_classification", "review_proposal",
            }
            for tool in tools:
                assert tool.annotations.read_only_hint is True
                assert tool.annotations.destructive_hint is False
                assert tool.annotations.open_world_hint is False
                assert tool.output_schema
                properties = set(tool.input_schema["properties"])
                assert not properties.intersection({"url", "command", "path", "filename", "token"})

            evidence = fixture("testdata/evidence_checkout_api.json")
            result = await session.call_tool("compute_baseline", {"evidence": evidence})
            assert not result.is_error
            measured = result.structured_content
            assert measured["status"] == "measured"
            baseline = measured["baseline"]
            assert baseline["service"] == evidence["service"]
            assert len(measured["input_sha256"]) == 64

            result = await session.call_tool("measure_drift", {"baseline": baseline, "evidence": evidence})
            assert result.structured_content["status"] == "measured"
            assert result.structured_content["human_review_required"] is True

            signal = fixture("analysis/evals/fixtures/drift/latency_regression.json")
            report = fixture("analysis/evals/recorded/drift/latency_regression_response.json")
            result = await session.call_tool("review_classification", {"signal": signal, "report": report})
            assert result.structured_content["status"] == "admissible"
            assert "latency_regression" in result.structured_content["permitted_classifications"]
            assert result.structured_content["report_checked"] is True

            for field, value in (("rel_deviation", 999), ("breach_magnitude", 0)):
                altered = copy.deepcopy(signal)
                target = altered["indicators"][0] if field == "rel_deviation" else altered["dominant_signal"]
                target[field] = value
                result = await session.call_tool("review_classification", {"signal": altered})
                assert result.structured_content["status"] == "abstained"
                assert "conflicts with measured values" in result.structured_content["reason"]

            bad_signal = copy.deepcopy(signal)
            bad_signal["indicators"] = []
            result = await session.call_tool("review_classification", {"signal": bad_signal})
            assert result.structured_content["status"] == "abstained"

            stamped = copy.deepcopy(report)
            # Use a valid constraint object, then bind it to another input digest.
            accepted = await session.call_tool("review_classification", {"signal": signal})
            stamped["evidence_constraint"] = dict(accepted.structured_content["evidence_constraint"])
            stamped["evidence_constraint"]["input_sha256"] = "0" * 64
            result = await session.call_tool("review_classification", {"signal": signal, "report": stamped})
            assert result.structured_content["status"] == "abstained"

            bad_report = copy.deepcopy(report)
            bad_report["service"] = "wrong-service"
            result = await session.call_tool("review_classification", {"signal": signal, "report": bad_report})
            assert result.structured_content["status"] == "abstained"

            bad_report = copy.deepcopy(report)
            bad_report["likely_cause"] = "Observed 99999999 ms latency and 99999999% error rate."
            result = await session.call_tool("review_classification", {"signal": signal, "report": bad_report})
            assert result.structured_content["status"] == "abstained"

            proposal_baseline = fixture("analysis/evals/fixtures/web_api_baseline.json")
            proposal = fixture("analysis/evals/recorded/web_api_baseline_response.json")
            result = await session.call_tool("review_proposal", {"baseline": proposal_baseline, "proposal": proposal})
            assert result.structured_content["status"] == "admissible"
            proposal["service"] = "wrong-service"
            result = await session.call_tool("review_proposal", {"baseline": proposal_baseline, "proposal": proposal})
            assert result.structured_content["status"] == "abstained"

            too_large = copy.deepcopy(evidence)
            too_large["oversize"] = "x" * (2 * 1024 * 1024)
            result = await session.call_tool("compute_baseline", {"evidence": too_large})
            assert result.structured_content["status"] == "abstained"
            assert "2 MiB" in result.structured_content["reason"]

            mismatched = copy.deepcopy(evidence)
            mismatched["namespace"] = "other-namespace"
            result = await session.call_tool("measure_drift", {"baseline": baseline, "evidence": mismatched})
            assert result.structured_content["status"] == "abstained"

    # No artifact files or reference mutations are performed by the tools.
    assert list(tmp_path.iterdir()) == []
