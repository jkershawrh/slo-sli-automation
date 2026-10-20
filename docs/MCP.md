# Review SLOscope evidence through MCP

Lab delivery is tracked in [INTEL-83](https://redhat.atlassian.net/browse/INTEL-83) under
INTEL-44, with Publishing House [RHDPCD-2154](https://redhat.atlassian.net/browse/RHDPCD-2154)
and the delivery repository [rhpds/sloscope-lab](https://github.com/rhpds/sloscope-lab).
The reusable engine and this optional adapter remain in the upstream source repository.

SLOscope's optional MCP server lets a compatible local assistant review lab evidence with
the same deterministic constraints used by the CLI/API. It does not generate model responses,
collect telemetry, write artifacts or execute remediation. It exposes four tools:

- `compute_baseline`: compute a baseline from an inline evidence bundle.
- `measure_drift`: compare inline evidence with a supplied reference baseline, preserving the reference.
- `review_classification`: inspect permitted classes, or check an existing report against its evidence.
- `review_proposal`: check a proposal's identity, measurements, numeric citations and target constraints.

All tools are annotated read-only, non-destructive, idempotent and closed-world. Their inputs
are JSON artifacts, not URLs, commands or filesystem paths. Each artifact is limited to 2 MiB.
The server binds stdio only and exposes no deployment, shell, Kubernetes mutation, model call,
network listener or file-store capability. Add external integrations only after their own access
and evidence contracts have been reviewed.

## Install and start

Use Python 3.11 for the tested MCP integration. From the SLOscope checkout:

```bash
python3.11 -m venv .venv-mcp
.venv-mcp/bin/python -m pip install -r requirements.txt -r requirements-mcp.txt
.venv-mcp/bin/python integrations/mcp_server.py
```

The process waits for MCP JSON-RPC over stdin/stdout; it is not a web server. The MCP SDK writes
operational logging to stderr. Exit with Ctrl-C when starting it manually. Normally your MCP host
starts and stops it for you.

A generic MCP host configuration is shown below. Replace both paths with absolute paths on the
machine running the host. No API key or cluster credential is required by this adapter:

```json
{
  "mcpServers": {
    "sloscope-evidence-review": {
      "command": "/absolute/path/to/sloscope/.venv-mcp/bin/python",
      "args": ["/absolute/path/to/sloscope/integrations/mcp_server.py"]
    }
  }
}
```

Configuration format and tool-approval controls depend on the host. This file alone does not
install the integration into a host or grant it access. Use the host's normal review process.

## A lab review sequence

1. Supply the synthetic `testdata/evidence_checkout_api.json` artifact to `compute_baseline`.
2. Supply a known reference and an evidence window to `measure_drift`.
3. Inspect `review_classification`'s permitted labels before reviewing a model report. Include
   the report to check its service, class, severity, numeric citations and no-actuation boundary.
4. Review a proposal against its exact baseline. Inspect the returned input hashes and review
   reasons; retain human approval before adopting any target or recommendation.

`abstained` means the input did not support a verdict. Missing or conflicting measurements,
insufficient coverage, malformed artifacts and unsupported numeric claims must not become a
successful classification through a recorded fallback. `admissible` means the implemented
schema/numeric checks passed. It does **not** authenticate telemetry provenance, independently
verify causal prose, establish alert firing, or approve a deployment or service commitment.

The assistant can see the artifacts you pass to these tools. Use synthetic or sanitized lab
artifacts first; inspect telemetry and remove credentials/customer data before providing them
to a host. The adapter does not discover files or read an artifact store on your behalf.

## Validate the protocol

The integration tests launch a real stdio server, initialize an MCP client, discover the tool
schemas/annotations and call the tools. They verify valid review, abstention and absence of
mutation/file/network arguments. Run them independently of the core dependency set:

```bash
.venv-mcp/bin/python -m pip install pytest pytest-asyncio
.venv-mcp/bin/python -m pytest tests/mcp -q
```

The core test/installation path remains unchanged when the optional MCP requirements are not
installed. See the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
for protocol and host integration details.
