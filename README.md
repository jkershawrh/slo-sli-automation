# sloscope

Evidence-based SLO/SLI generator and drift detector. Queries Prometheus/Thanos telemetry, computes deterministic baselines, and uses an LLM to propose defensible SLOs and classify drift -- every target traces back to observed history.

## How it works

Two-stage architecture, applied to both SLO generation and drift detection:

1. **Stage one is deterministic.** Compute empirical baselines (or deviation signals) from telemetry in code. No LLM touches this stage. The numbers are measured, reproducible, and auditable.

2. **Stage two is judgment.** Hand the computed evidence to an LLM. It proposes SLO targets with headroom, classifies drift with remediation plans, and writes rationale citing the specific values it was given. It never fabricates a number.

```
                    Prometheus/Thanos
                          |
                    [Evidence Collection]
                          |
                    [Deterministic Baseline]  <-- stage one (code)
                          |
                    [LLM Proposal/Classification]  <-- stage two (judgment)
                          |
              +-----------+-----------+
              |           |           |
         OpenSLO     Prometheus   Audit Bundle
          YAML       Alert Rules    (traceable)
```

## Quick start

### Prerequisites

- Go 1.22+
- Python 3.9+
- `pip install -r requirements.txt`

### Environment variables

```bash
export PROM_URL="https://thanos-querier.example.com:9091"  # Prometheus/Thanos endpoint
export PROM_TOKEN="..."                                     # Optional bearer token
export LLM_BASE_URL="https://your-llm-endpoint/v1"         # OpenAI-compatible API
export LLM_API_KEY="..."                                    # API key
export LLM_MODEL="granite-3-2-8b-instruct"                 # Model name
```

### Generate SLOs

```bash
# Build
make build

# Dry run (no LLM needed -- computes baseline only)
./bin/sloscope generate \
  --service checkout-api \
  --namespace payments \
  --lookback 30d \
  --out ./out/checkout-api \
  --dry-run

# Full run (requires LLM credentials)
./bin/sloscope generate \
  --service checkout-api \
  --namespace payments \
  --lookback 30d \
  --type service \
  --maturity growing \
  --out ./out/checkout-api

# From a pre-collected evidence file (no Prometheus needed)
./bin/sloscope generate \
  --service checkout-api \
  --evidence testdata/evidence_checkout_api.json \
  --out ./out/checkout-api
```

**Output artifacts:**

| File | Description |
|------|-------------|
| `evidence.json` | Raw telemetry from Prometheus with provenance |
| `baseline.json` | Deterministic empirical baseline (versioned contract) |
| `proposal.json` | LLM-proposed SLOs with targets, rationale, headroom |
| `openslo.yaml` | OpenSLO v1 spec with correct `op: lte/gte` per signal |
| `prometheus-rules.yaml` | Recording rules + multi-window multi-burn-rate alerts |
| `audit-bundle.json` | Full evidence chain with SHA-256 content hashes |

### Detect drift

```bash
# Dry run (deterministic deviation only, no LLM)
./bin/sloscope drift \
  --service checkout-api \
  --baseline ./out/checkout-api/baseline.json \
  --window 1h \
  --out ./out/checkout-api/drift \
  --dry-run

# Full run (LLM classifies drift and proposes remediation)
./bin/sloscope drift \
  --service checkout-api \
  --baseline ./out/checkout-api/baseline.json \
  --evidence testdata/drift_live_latency_regression.json \
  --type service \
  --out ./out/checkout-api/drift
```

**Output artifacts:**

| File | Description |
|------|-------------|
| `drift-signal.json` | Per-indicator deviation, band breach, rule-based classification |
| `drift-report.json` | LLM classification with prioritized remediation plan |
| `drift-summary.txt` | Human-readable drift report |
| `drift-audit-bundle.json` | Full evidence chain with content hashes |

## Target directionality

The four golden signals have different "directions of goodness." sloscope encodes this explicitly:

| SLI Type | Direction | target_op | Target meaning |
|----------|-----------|-----------|----------------|
| Latency | Lower is better | `lte` | p99 at or below X ms |
| Error rate | Lower is better | `lte` | Ratio at or below X |
| Availability | Higher is better | `gte` | Ratio at or above X |
| Throughput | Higher is better | `gte` | RPS at or above X |
| Saturation | Lower is better | `lte` | Utilization at or below X |

Targets always include headroom based on observed standard deviation. The tool never proposes a target equal to the observed value.

## Maturity tiers

The `--maturity` flag controls how aggressively targets are set:

| Tier | Headroom | Use case |
|------|----------|----------|
| `new` | 2-3 stddev | New services establishing baselines |
| `growing` | 1-2 stddev | Services with some history (default) |
| `mature` | 0.5-1 stddev | Stable services ready for tight SLOs |

## Context types

The `--type` flag adapts the tool for different workloads:

- `service` (default) -- application metrics: HTTP latency, request rates, error rates
- `infra` -- infrastructure metrics: node health, network throughput, resource utilization

## Drift taxonomy

The drift detector classifies deviations into a fixed taxonomy:

| Class | Direction | Severity signal |
|-------|-----------|-----------------|
| `latency_regression` | Latency increased | Breach magnitude |
| `latency_improvement` | Latency decreased | Positive change |
| `error_rate_elevation` | Error rate increased | Breach magnitude |
| `error_rate_reduction` | Error rate decreased | Positive change |
| `throughput_collapse` | Throughput decreased | Breach magnitude |
| `throughput_surge` | Throughput increased | Breach magnitude |
| `saturation_approach` | Resource utilization increased | Breach magnitude |
| `availability_drop` | Availability decreased | Breach magnitude |
| `distribution_shift` | Mixed signals (e.g., p50 stable, p99 diverged) | Pattern analysis |
| `no_significant_drift` | All within tolerance | No breach |

For negative drift, the LLM produces a prioritized remediation plan:
- **Immediate**: blast radius assessment, rollback consideration
- **Short-term**: targeted investigation based on telemetry patterns
- **Long-term**: prevention through monitoring, capacity planning, or architectural changes

Each recommendation includes an evidence basis and a verification method.

## Architecture

```
cmd/sloscope/              Go CLI (generate + drift subcommands)
internal/
  config/                  Environment variable resolution
  prom/                    Prometheus/Thanos query client
  pipeline/                Go-to-Python subprocess orchestration
  drift/                   Baseline loading, live sampling, deviation input
  render/                  OpenSLO, Prometheus rules, audit bundle, drift report
  schema/                  JSON schema validation (go:embed)
analysis/
  baseline.py              Deterministic baseline computation
  deviation.py             Deterministic deviation + rule-based classifier
  propose.py               LLM SLO proposal stage
  classify.py              LLM drift classification stage
  consistency.py           Shared consistency validation (directionality, margins)
  serialize.py             Canonical JSON serializer (sorted keys, fixed floats)
  schemas/                 JSON schemas (single source of truth)
  evals/                   Eval fixtures, rubrics, recorded responses, runners
  tests/                   pytest test suite
testdata/                  Recorded Prometheus fixtures for hermetic tests
scripts/
  preflight.sh             Environment readiness checks
  verify.sh                Full hermetic verification (25 checks)
```

## Development methodology

Three disciplines, each governing the part of the system it fits:

- **TDD** governs deterministic code: baseline math, deviation computation, renderers. Failing test first, implement to green.
- **CDD** governs boundaries: JSON schemas frozen before implementation, validated on both Go and Python sides. The baseline artifact is a versioned contract.
- **EDD** governs LLM stages: eval suites with fixtures, rubrics, hard gates, and scored dimensions. Prompts developed against the suite until the eval grid is green.

## Testing

```bash
# Preflight (environment checks)
bash scripts/preflight.sh

# Full hermetic verification (no live cluster or LLM needed)
make build && bash scripts/verify.sh

# Unit tests only
make test

# Go tests only
go test ./... -v

# Python tests only
python3 -m pytest analysis/tests/ -v
```

**Test coverage:** 416 tests (69 Go + 347 Python), 25 verification checks, eval grids across 13 scenarios (3 proposal + 10 drift).

## Schemas

All JSON schemas live in `analysis/schemas/` and are the single source of truth:

| Schema | Version | Description |
|--------|---------|-------------|
| `evidence.schema.json` | 1 | Raw telemetry from Prometheus |
| `baseline.schema.json` | 1 | Deterministic empirical baseline (cross-doc contract) |
| `proposal.schema.json` | 2 | LLM SLO proposal with target_op and headroom |
| `drift-signal.schema.json` | 1 | Deterministic deviation measurements |
| `drift-report.schema.json` | 1 | LLM drift classification with remediation plan |

## License

See repository for license details.
