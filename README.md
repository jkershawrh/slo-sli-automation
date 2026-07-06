# sloscope

Evidence-based SLO/SLI generator and drift detector for OpenShift services and infrastructure. Built for the Red Hat Demo Platform (RHDP) to replace guesswork-driven SLO targets with defensible, data-grounded objectives backed by Prometheus/Thanos telemetry and IBM Granite inference.

## Why this exists

As RHDP consolidates from GPU-heavy multi-model deployments to a leaner Intel Xeon 6 CPU-only architecture for Summit Connect events, reliability becomes the constraint. SLO targets set by gut feel ("let's aim for 99.9%") break in two ways: they are either unachievable (triggering alert fatigue) or too loose (hiding real degradation during live demos).

sloscope solves this by grounding every SLO in observed telemetry:

- A service running at 93.2% availability gets an incremental improvement target, not an aspirational 99.9% that will never be met
- A model-serving endpoint with high p99 variance gets wider headroom so normal jitter does not page the on-call during a Summit Connect session
- When latency regresses after a deployment, the drift detector identifies whether it is a tail-latency issue (p99 up, p50 stable) or systemic slowdown (everything up), and recommends targeted investigation rather than generic "check the logs"

## How it works

Two stages. Evidence first, judgment second.

**Stage one is deterministic.** Query Prometheus/Thanos, compute empirical baselines in code: latency percentiles, error rates, throughput distribution, availability, saturation. No LLM touches this. The numbers are measured, reproducible, and auditable.

**Stage two is judgment.** Hand the computed evidence to an LLM (Granite on the MAAS LiteLLM proxy, or any OpenAI-compatible endpoint). It proposes SLO targets with stddev-based headroom, classifies drift with prioritized remediation plans, and writes rationale citing specific observed values. It never fabricates a number, and it never actuates.

```
          OpenShift Cluster (MAAS / rac-MAAS)
                    |
              Prometheus/Thanos
                    |
            [Evidence Collection]           <-- PromQL queries, provenance tracked
                    |
            [Deterministic Baseline]        <-- stage one: code, reproducible
                    |
            [LLM Proposal/Classification]   <-- stage two: Granite via LiteLLM
                    |
          +---------+---------+
          |         |         |
     OpenSLO   Prometheus   Audit Bundle
      YAML     Alert Rules   (SHA-256 hashes, full chain)
```

## Target audience

- **RHDP platform engineers** managing the MAAS clusters, model-serving endpoints, and demo applications that must stay reliable through Summit Connect
- **SREs** operating services on OpenShift who need SLOs derived from actual performance data, not aspirational targets
- **Demo lab owners** who need to know if their lab's performance has drifted from its baseline before a live event

## Quick start

### Prerequisites

- Go 1.22+
- Python 3.9+
- `pip install -r requirements.txt`

### Environment

```bash
# Prometheus/Thanos (Thanos Querier route on OpenShift, or any compatible endpoint)
export PROM_URL="https://thanos-querier.openshift-monitoring.svc:9091"
export PROM_TOKEN="..."                                     # Optional bearer token for in-cluster Thanos

# LLM (OpenAI-compatible -- LiteLLM proxy on MAAS, vLLM, RHEL AI, or any endpoint)
export LLM_BASE_URL="https://litellm.example.com/v1"
export LLM_API_KEY="..."
export LLM_MODEL="granite-3-2-8b-instruct"
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

## Fits into the RHDP toolchain

sloscope complements the broader RHDP operations toolkit:

- **LiftOff** validates that a lab CAN run on the target hardware (5-gate readiness pipeline)
- **sloscope** validates that it IS running reliably over time (evidence-based SLOs + drift detection)
- **NovaScan** monitors cluster capacity (can we fit more labs?)
- **DarkScope** scans for security issues

Together they cover the lifecycle: readiness, reliability, capacity, security.

## Architecture

```
cmd/sloscope/              Go CLI (generate + drift subcommands)
internal/
  config/                  Environment variable resolution (no secrets on disk)
  prom/                    Prometheus/Thanos query client (bearer token auth)
  pipeline/                Go-to-Python subprocess orchestration (JSON stdin/stdout)
  drift/                   Baseline loading + validation, deviation input assembly
  render/                  OpenSLO, Prometheus rules, audit bundle, drift report
  schema/                  JSON schema validation (go:embed from analysis/schemas/)
analysis/
  baseline.py              Deterministic baseline computation (histogram percentiles, rates)
  deviation.py             Deterministic deviation + rule-based first-pass classifier
  propose.py               LLM SLO proposal stage (repair loop, consistency checks)
  classify.py              LLM drift classification (evidence-based remediation plans)
  consistency.py           Shared validation: directionality, margins, looseness bounds
  serialize.py             Canonical JSON (sorted keys, 2-space indent, 6 sig digits)
  schemas/                 JSON schemas (single source of truth, embedded in Go via go:embed)
  evals/                   Eval fixtures (13 scenarios), rubrics, recorded responses
  tests/                   pytest suite (347 tests)
testdata/                  Recorded Prometheus fixtures for hermetic CI
scripts/
  preflight.sh             Environment readiness (Go, Python, Prometheus, LLM, promtool)
  verify.sh                Full hermetic verification: 25 checks, no live deps needed
```

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

416 tests (69 Go + 347 Python). 25 verification checks. Eval grids across 13 scenarios (3 proposal + 10 drift). Validated live against `granite-3-2-8b-instruct` on the MAAS GPU tier.

## Schemas

| Schema | Version | Purpose |
|--------|---------|---------|
| `evidence.schema.json` | 1 | Raw Prometheus telemetry with provenance |
| `baseline.schema.json` | 1 | Deterministic empirical baseline (versioned contract for drift) |
| `proposal.schema.json` | 2 | LLM SLO proposal with target_op, headroom, maturity tier |
| `drift-signal.schema.json` | 1 | Deterministic deviation measurements |
| `drift-report.schema.json` | 1 | LLM drift classification with remediation plan |
