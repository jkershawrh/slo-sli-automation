# sloscope

An open framework for replacing guesswork-driven SLO targets with defensible objectives grounded in Prometheus/Thanos telemetry and LLM-powered analysis. Works with any Prometheus/Thanos endpoint, any OpenAI-compatible LLM, and any OpenShift or Kubernetes cluster.

## Why this exists

SLO targets set by gut feel ("let's aim for 99.9%") break in two ways: they are either unachievable (triggering alert fatigue) or too loose (hiding real degradation). This is the aspirational trap -- teams pick round numbers that sound right, then either drown in false alerts or miss genuine incidents.

The second failure mode is directional blindness. Not all signals improve the same way. Latency and error rates are "lower is better." Availability and throughput are "higher is better." Generic dashboards that ignore directionality produce nonsensical targets.

sloscope solves both problems by grounding every SLO in observed telemetry:

- A service running at 93.2% availability gets an incremental improvement target, not an aspirational 99.9% that will never be met
- A model-serving endpoint with high p99 variance gets wider headroom so normal jitter does not page the on-call during a critical window
- When latency regresses after a deployment, the drift detector identifies whether it is a tail-latency issue (p99 up, p50 stable) or systemic slowdown (everything up), and recommends targeted investigation rather than generic "check the logs"

## How it works

Two stages. Evidence first, judgment second.

**Stage one is deterministic.** Query Prometheus/Thanos for metrics, optionally enrich with traces (Tempo/Jaeger) and logs (Loki/Elasticsearch), then compute empirical baselines in code: latency percentiles, error rates, throughput distribution, availability, saturation, dependency latency breakdowns, and error category distributions. No LLM touches this. The numbers are measured, reproducible, and auditable.

**Stage two is judgment.** Hand the computed evidence to an LLM (any OpenAI-compatible endpoint -- LiteLLM, vLLM, Ollama, or a hosted API). It proposes both an SLO target (objective -- where you aim, tighter than observed) and an SLA target (commitment -- what you guarantee, with headroom). It classifies drift with prioritized remediation plans and writes rationale citing specific observed values. It never fabricates a number, and it never actuates.

```
          Kubernetes / OpenShift Cluster
                    |
              Prometheus/Thanos
                    |
            [Evidence Collection]           <-- PromQL queries, provenance tracked
                    |
            [Deterministic Baseline]        <-- stage one: code, reproducible
                    |
            [LLM Proposal/Classification]   <-- stage two: any OpenAI-compatible endpoint
                    |
          +---------+---------+
          |         |         |
     OpenSLO   Prometheus   Audit Bundle
      YAML     Alert Rules   (SHA-256 hashes, full chain)
```

## Target audience

- **Platform engineers** running services on Kubernetes or OpenShift who need SLOs derived from actual performance data, not aspirational targets
- **SREs and DevOps teams** responsible for service reliability who want defensible error budgets and evidence-based alerting thresholds
- **Operations teams** who need to know if a service's performance has drifted from its baseline before a release, migration, or critical event

## Quick start

### Prerequisites

- Go 1.22+
- Python 3.9+
- `pip install -r requirements.txt`

### Environment

```bash
# Metrics (required)
export PROM_URL="https://thanos-querier.example.com:9091"
export PROM_TOKEN="..."                    # Optional bearer token

# Traces (optional -- enriches evidence with dependency latency breakdowns)
export TEMPO_URL="https://tempo.example.com:3200"
export TEMPO_TOKEN="..."

# Logs (optional -- enriches evidence with error category breakdowns)
export LOKI_URL="https://loki.example.com:3100"
export LOKI_TOKEN="..."

# LLM (any OpenAI-compatible endpoint)
export LLM_BASE_URL="https://llm.example.com/v1"
export LLM_API_KEY="..."
export LLM_MODEL="qwen3-235b"             # or any model that handles structured JSON
```

### Generate SLOs

```bash
make build

# Dry run -- computes baseline from telemetry, no LLM needed
./bin/sloscope generate \
  --service model-serving-api \
  --namespace inference \
  --lookback 30d \
  --type service \
  --maturity growing \
  --out ./out/model-serving-api \
  --dry-run

# Full run -- baseline + LLM proposal + rendered outputs
./bin/sloscope generate \
  --service model-serving-api \
  --namespace inference \
  --lookback 30d \
  --type service \
  --maturity growing \
  --out ./out/model-serving-api

# From a pre-collected evidence file (offline or CI use)
./bin/sloscope generate \
  --service model-serving-api \
  --evidence testdata/evidence_checkout_api.json \
  --out ./out/model-serving-api
```

**Outputs:** `evidence.json`, `baseline.json`, `proposal.json`, `openslo.yaml`, `prometheus-rules.yaml`, `audit-bundle.json`

### Detect drift

```bash
# Dry run -- deterministic deviation measurement, no LLM
./bin/sloscope drift \
  --service model-serving-api \
  --baseline ./out/model-serving-api/baseline.json \
  --window 1h \
  --type service \
  --out ./out/model-serving-api/drift \
  --dry-run

# Full run -- LLM classifies drift type and proposes remediation
./bin/sloscope drift \
  --service model-serving-api \
  --baseline ./out/model-serving-api/baseline.json \
  --window 1h \
  --type service \
  --out ./out/model-serving-api/drift
```

**Outputs:** `drift-signal.json`, `drift-report.json`, `drift-summary.txt`, `drift-audit-bundle.json`

## The four golden signals

sloscope encodes directionality explicitly for each signal -- the comparison operator determines what "meeting the SLO" means:

| Signal | SLI Type | target_op | Meaning | Example |
|--------|----------|-----------|---------|---------|
| Latency | `latency` | `lte` | p99 at or below target | p99 <= 600ms |
| Errors | `error_rate` | `lte` | Error ratio at or below target | error_rate <= 0.003 |
| Traffic | `throughput` | `gte` | RPS at or above target | rps >= 4.0 |
| Saturation | `saturation` | `lte` | Utilization at or below target | cpu <= 0.80 |
| (Derived) | `availability` | `gte` | Availability at or above target | availability >= 0.996 |

Targets always include headroom based on observed variance. The tool never proposes a target equal to the observed value -- there is always margin so normal fluctuation does not trigger alerts.

## SLI / SLO / SLA hierarchy

sloscope enforces a strict three-level hierarchy:

| Level | What it is | Direction vs observed |
|-------|-----------|----------------------|
| **SLI** (Indicator) | The measurement -- p99 latency, error rate, availability | This is the 30-day average |
| **SLO** (Objective) | Where you aim -- aspirational but reachable | Tighter than observed |
| **SLA** (Agreement) | What you guarantee -- the alerting boundary | Looser than observed, with stddev headroom |

For a latency SLI at 500ms: the SLO might be 450ms (aim lower), the SLA ceiling might be 595ms (guarantee you stay below). For availability at 99.8%: the SLO might be 99.85% (aim higher), the SLA floor might be 99.68% (guarantee you stay above).

## Incremental targets, not aspirational jumps

sloscope computes targets from observed performance plus stddev-based headroom, scaled by maturity tier:

| Tier | Headroom | When to use |
|------|----------|-------------|
| `new` | 2-3 stddev | New services, first baseline, wide margins |
| `growing` | 1-2 stddev | Services with history, standard targets (default) |
| `mature` | 0.5-1 stddev | Stable services, tight SLOs, ready for promotion |

A service at 93.2% availability with 2% stddev gets a `growing` target of ~89.2% (2 stddev headroom below observed), not 99.9%. The rationale explains why, cites the specific numbers, and suggests what to fix to improve. Once the service stabilizes, `--maturity mature` tightens the target incrementally.

## Context types

The `--type` flag adapts metric collection and LLM reasoning for the workload:

- **`service`** (default) -- application-level: HTTP latency histograms, request/error rates, availability. Reasoning focuses on API performance, deployment impact, downstream dependencies.
- **`infra`** -- infrastructure-level: node CPU/memory, network throughput, storage I/O, pod scheduling. Reasoning focuses on capacity planning, node health, resource exhaustion, blast radius.

## Drift detection and remediation

The drift detector classifies deviations into a fixed 10-class taxonomy, then produces evidence-based remediation:

| Class | What it means |
|-------|---------------|
| `latency_regression` | Latency increased beyond tolerance band |
| `latency_improvement` | Latency decreased (positive -- recommend baseline update) |
| `error_rate_elevation` | Error rate spiked beyond tolerance |
| `error_rate_reduction` | Error rate dropped (positive) |
| `throughput_collapse` | Traffic fell below tolerance |
| `throughput_surge` | Traffic spiked above tolerance |
| `saturation_approach` | CPU/memory approaching limits |
| `availability_drop` | Availability fell below tolerance |
| `distribution_shift` | Mixed signals (e.g., p50 stable but p99 diverged -- tail issue) |
| `no_significant_drift` | All indicators within tolerance bands |

For negative drift, remediation is prioritized and grounded in telemetry:

- **Immediate**: assess blast radius, consider rollback if recent deployment. "p99 breached at 22.5x while p50 shifted only 1.2x -- this is a tail-latency issue, not systemic. Check slow queries and downstream timeouts."
- **Short-term**: targeted investigation. "Throughput down + error rate up correlates with the CPU saturation approaching 85% -- investigate resource limits before adding replicas."
- **Long-term**: prevention. "High latency variance (stddev 25% of p99) suggests heterogeneous workload sizes -- consider job queue prioritization."

Each recommendation includes a verification method: "Re-run drift detection after 1h to verify p99 returns within tolerance band [300ms, 700ms]."

For positive drift, the tool recommends updating the baseline and suggests tighter SLO targets with specific values.

## Architecture

```
cmd/sloscope/              Go CLI (generate + drift subcommands)
internal/
  config/                  Environment variable resolution (no secrets on disk)
  prom/                    Prometheus/Thanos query client (bearer token auth)
  pipeline/                Go-to-Python subprocess orchestration (JSON stdin/stdout)
  drift/                   Baseline loading + validation, deviation input assembly
  render/                  OpenSLO, Prometheus rules, audit bundle, drift report
  traces/                  OpenTelemetry trace correlation for SLI evidence
  logs/                    Structured log analysis for error-rate SLIs
  schema/                  JSON schema validation (go:embed from analysis/schemas/)
analysis/
  baseline.py              Deterministic baseline computation (histogram percentiles, rates)
  deviation.py             Deterministic deviation + rule-based first-pass classifier
  propose.py               LLM SLO proposal stage (repair loop, consistency checks)
  classify.py              LLM drift classification (evidence-based remediation plans)
  consistency.py           Shared validation: directionality, margins, looseness bounds
  serialize.py             Canonical JSON (sorted keys, 2-space indent, 6 sig digits)
  schemas/                 JSON schemas (single source of truth, embedded in Go via go:embed)
  evals/                   Eval fixtures (14 scenarios), rubrics, recorded responses
  tests/                   pytest suite (417 tests)
testdata/                  Recorded Prometheus fixtures for hermetic CI
scripts/
  preflight.sh             Environment readiness (Go, Python, Prometheus, LLM, promtool)
  verify.sh                Full hermetic verification: 29 checks, no live deps needed
```

## Frontend

Three-mode single-page app (React + Vite): **slides** for presentation walkthroughs, **demo** for fixture-backed SLO generation against the backend API, and **lab** for hands-on guided exercises. Served as static files by the backend in production.

## Backend API

FastAPI server (`backend/server.py`) exposing the demo pipeline as REST endpoints: fixture evidence loading, baseline computation, SLO proposal (with LLM fallback to recorded responses), drift signal/classification, and artifact rendering (OpenSLO YAML + Prometheus rules). Serves the frontend SPA in production. Live Prometheus/Thanos collection remains in the Go CLI.

By default the backend allows local development origins. Set `SLOSCOPE_CORS_ORIGINS` to a comma-separated list for deployed frontends, or set `SLOSCOPE_ALLOW_ANY_ORIGIN=true` to explicitly allow wildcard CORS for throwaway demos.

## Development methodology

Three disciplines govern the codebase, each matched to the code it fits:

- **TDD** -- deterministic code (baseline math, deviation, renderers): failing test first, implement to green
- **CDD** -- boundaries (5 JSON schemas, Go/Python subprocess contract): schema frozen before implementation, validated on both sides
- **EDD** -- LLM stages (proposal + drift classification): eval suites with hard gates and scored dimensions, prompts tuned until the grid is green

Red/green matrix enforced by `scripts/verify.sh`. No milestone starts until the previous is green.

## Testing

```bash
# Preflight (checks Go, Python, deps, connectivity)
bash scripts/preflight.sh

# Full hermetic verification (no cluster, no LLM, no network)
make build && bash scripts/verify.sh

# Unit tests
make test                              # Go + Python
go test ./... -v                       # Go only
python3 -m pytest analysis/tests/ -v   # Python only
```

525 tests (83 Go + 417 Python + 23 frontend). 29 verification checks. Eval grids across 14 scenarios (4 proposal + 10 drift). Validated live against `granite-3-2-8b-instruct` and `qwen3-235b`.

## Schemas

| Schema | Version | Purpose |
|--------|---------|---------|
| `evidence.schema.json` | 1-2 | Raw telemetry (v1: metrics only, v2: metrics + traces + logs) |
| `baseline.schema.json` | 1 | Deterministic empirical baseline (versioned contract for drift) |
| `proposal.schema.json` | 3 | LLM SLO proposal with target_op, headroom, maturity tier |
| `drift-signal.schema.json` | 1 | Deterministic deviation measurements |
| `drift-report.schema.json` | 1 | LLM drift classification with remediation plan |

## Benchmarks

Measured on the current codebase (`scripts/benchmark.py`):

| Metric | Value |
|--------|-------|
| Baseline computation (metrics) | 67ms avg |
| Baseline computation (metrics + traces + logs) | 41ms avg |
| Deviation computation | 34-55ms avg |
| E2E generate dry-run | 254ms |
| E2E drift dry-run | 221ms |
| Proposal eval grid | 4/4 passed |
| Drift eval grid | 10/10 passed |
| LLM proposal (qwen3-235b) | 100% pass, 57s avg |
| LLM proposal (granite-3-2-8b) | 0% pass (fails directional consistency) |

Full results in `benchmark-results.json`. Whitepaper with analysis in `docs/whitepaper.md`.

## Deployment

```bash
# Container build and push
make container-build
make container-push

# Deploy to OpenShift/Kubernetes
oc apply -f deploy/deployment.yaml
```

The container image runs the FastAPI backend with the built frontend on port 8080. Configure LLM credentials via a Secret.

## Local development

```bash
make dev           # Starts backend (port 8080) + frontend (port 3000)
make test-all      # Go + Python + frontend tests
make verify        # Full 29-check verification
```
