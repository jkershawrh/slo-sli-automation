# Claude Code Build Prompt: Evidence-Based SLO/SLI Generator

Doc 1 of 2. This document builds the generator. Doc 2 builds the drift detector and remediation layer on top of the baseline artifact this document produces.

Paste this whole document into Claude Code (`claude`) from the root of the working directory. It is self-contained. Follow the build order exactly and do not move to the next milestone until the current one is green by its governing discipline.

---

## 1. Role and objective

You are a senior platform engineer building a command-line tool that generates SLI and SLO definitions for a service by grounding them in evidence.

The tool queries historical telemetry from Prometheus/Thanos, computes empirical baselines deterministically in code, and then uses an LLM to propose defensible SLI selections and SLO targets that are justified by those baselines. Every threshold must trace back to observed history. The LLM proposes and justifies. It never fabricates a number.

The output is a set of standards-based artifacts (OpenSLO YAML plus Prometheus rules) accompanied by an audit bundle that captures the evidence, the computed baselines, and the LLM rationale so any SLO can be defended after the fact.

## 2. Core philosophy (do not violate)

Two stages, evidence first.

Stage one is deterministic. Given historical telemetry, compute empirical baselines in code: latency percentiles (p50, p90, p95, p99), success and error rates, request throughput distribution, saturation where available, and availability over the window. No LLM touches this stage. These numbers are measured, reproducible, and auditable.

Stage two is judgment. Hand the computed baselines to the LLM as evidence. Its job is to decide which indicators matter for the service, what SLO target the evidence justifies and why, a sensible error budget, and a burn-rate alerting policy, plus a written rationale tied directly to the baseline values it was given. The LLM must select and justify. It must never invent a raw metric value. If it needs a number, it uses one from the baseline artifact.

Auditability is a first-class requirement. The final output always includes an audit bundle: the raw evidence, the deterministic baseline, and the LLM proposal with rationale, so the chain from observed history to proposed SLO is fully traceable.

## 3. Development methodology (TDD, CDD, EDD)

Three disciplines, each governing the part of the system it fits. Every milestone writes its tests, contracts, or evals first, then the implementation.

TDD (Test-Driven Development) governs all deterministic code: the Prometheus query layer, the baseline math, schema validation, and the three renderers. Write the failing test first, implement to green, refactor. For the baseline math, hand-compute expected percentiles for a small fixture and assert exact, reproducible equality before implementing anything.

CDD (Contract-Driven Development) governs every boundary. The four artifact schemas (evidence, baseline, proposal, output) and the Go to Python subprocess contract are written and frozen before the code that produces or consumes them. Both producer and consumer validate against the schema, and a contract test asserts each side honors it. The baseline artifact schema is a published, versioned contract because the future drift phase will consume it, so encode the drift phase read expectations as a contract test now, even though the drift phase is not built.

EDD (Eval-Driven Development) governs the LLM proposal stage, which is non-deterministic and cannot be asserted against an exact expected string. Instead, build an eval suite: a set of baseline fixtures (input scenarios) each paired with a rubric of properties the proposal must satisfy. Develop the prompt and the stage against the suite. Red means the rubric fails, green means it passes at threshold. The eval runs hermetically in CI against recorded model responses, and can also be run live against the endpoint for prompt tuning.

## 4. Non-goals for this version

- No drift detection in this build. But structure the baseline artifact so it can later serve as the reference baseline for a drift detector. Treat the baseline JSON as a stable, versioned contract.
- No web dashboard.
- No Datadog adapter. Prometheus/Thanos only.
- Do not hardcode any single model vendor. The LLM endpoint is configured through an OpenAI-compatible base URL and key.

## 5. Read before you write any code

1. Inspect the working directory for existing scaffolding, a prior repo, Makefile, or partial implementation. If any exists, read it fully and build on it rather than starting over. Report what you found before proceeding.
2. Confirm environment access. Print the resolved values (not secrets) for the Prometheus/Thanos URL and the model endpoint base URL. If either is unset, stop and say so.
3. Query one real service for a small window and print two or three example metric series (a latency histogram, a request-total counter, an error-total counter) so you confirm the metric names and label shape before writing the query layer. Do not assume metric names. The results from this live discovery step become the basis for the recorded fixtures in `testdata/`. The verification script uses these fixtures, not live queries.

Report findings from these three steps, then continue.

## 6. Environment and toolchain

- Target platform: OpenShift. Telemetry source: Prometheus/Thanos (Thanos Querier route in-cluster, or a provided URL).
- LLM: OpenAI-compatible chat completions endpoint (for example vLLM or RHEL AI). Base URL and API key come from environment variables. Never hardcode a vendor.
- Go 1.22+ for the core CLI.
- Python 3.11+ for the analysis stage.
- Config and secrets from environment variables. No config file in this version. Never write secrets to disk or logs.

Environment variables the tool reads:

- `PROM_URL` (Prometheus/Thanos query endpoint)
- `PROM_TOKEN` (optional bearer token for in-cluster Thanos)
- `LLM_BASE_URL` (OpenAI-compatible base URL)
- `LLM_API_KEY`
- `LLM_MODEL` (model name/id served at the endpoint)

Python dependencies are managed via `requirements.txt` with pinned versions.

## 7. Architecture

Go core owns: the CLI and its UX, config resolution, the Prometheus/Thanos query client, orchestration of the two analysis stages, JSON schema validation of every artifact, and rendering of final outputs (OpenSLO, Prometheus rules, audit bundle).

Python analysis owns: deterministic baseline computation from an evidence bundle, and the LLM proposal stage that reads the baseline and returns a schema-valid proposal.

The boundary between Go and Python is a subprocess call. Go invokes Python by script path (for example `python3 analysis/baseline.py` for stage one, `python3 analysis/propose.py` for stage two). The input JSON is written to stdin. The result JSON is read from stdout. Stderr carries log lines and error messages but is not parsed as structured data. Exit 0 means success with valid JSON on stdout. Non-zero exit means failure with a diagnostic on stderr. Go enforces a configurable timeout per subprocess call (default 60 seconds). Define and validate the JSON contract on both sides. This keeps each stage independently testable and lets the Python analysis run hermetically against fixtures.

Suggested repo layout (adjust to any existing scaffolding you found):

```
.
  cmd/sloscope/           Go CLI entrypoint
  internal/config/        env config resolution
  internal/prom/          Prometheus/Thanos client and queries
  internal/pipeline/      orchestration, subprocess boundary
  internal/render/        OpenSLO + Prometheus rules + audit bundle
  internal/schema/        embedded JSON schemas + validation
  analysis/
    baseline.py           deterministic baseline computation
    propose.py            LLM proposal stage
    schemas/              JSON schemas (shared source of truth)
    evals/                eval fixtures + rubric + runner
    tests/                pytest fixtures + unit tests
  scripts/
    preflight.sh
    verify.sh
  testdata/               recorded Prometheus and LLM responses for hermetic tests
  Makefile
  README.md
```

Note: `sloscope` is a placeholder name. Rename freely.

## 8. Interface contracts

### CLI

```
sloscope generate \
  --service checkout-api \
  --namespace payments \
  --lookback 30d \
  --out ./out/checkout-api

sloscope generate --service checkout-api --lookback 30d --dry-run
```

`--dry-run` runs the evidence-collection and baseline stages and prints the baseline artifact, but does not call the LLM and does not render final outputs. This must work with no LLM credentials present.

Exit codes: 0 on success, non-zero on any failure (unreachable Prometheus, empty evidence, schema-invalid artifact, LLM failure, render failure). Errors go to stderr with a clear cause.

### Evidence bundle (Go to Python, stage one input)

Contains the service identity, the lookback window, the data coverage ratio (fraction of the window with valid scrape data), and the raw query results from Prometheus (Go does not perform arithmetic on the series; aggregation is done in PromQL or by the Python baseline stage). Includes provenance: query strings used, timestamps, and the Prometheus endpoint. This provenance is carried through into the audit bundle unchanged. If the coverage ratio is below 0.90, emit a warning. If below 0.50, fail with an error rather than producing a low-confidence baseline.

### Baseline artifact (deterministic, stage one output)

Versioned. Contains, per indicator, the computed empirical values with the sample count and window they were derived from. For example latency percentiles from histogram buckets, error ratio over the window, request rate distribution, availability. No proposals, no prose, just measured values plus provenance. Availability is defined as `1 - (error_count / total_count)` over the lookback window. This is the artifact that a future drift detector will consume as its reference, so treat its schema as a stable contract and stamp it with a schema version using monotonic integer versioning starting at 1. Consumers declare the set of versions they support and reject anything outside that set.

Example baseline artifact structure:

```json
{
  "schema_version": 1,
  "service": "checkout-api",
  "namespace": "payments",
  "lookback_window": "30d",
  "generated_at": "2025-01-15T10:30:00Z",
  "indicators": {
    "latency": {
      "p50_ms": 42.3,
      "p90_ms": 128.7,
      "p95_ms": 195.4,
      "p99_ms": 412.1,
      "stddev_ms": 87.2,
      "sample_count": 8432100,
      "source_query": "histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))"
    },
    "error_rate": {
      "ratio": 0.0023,
      "stddev": 0.0008,
      "error_count": 19394,
      "total_count": 8432100,
      "source_query": "sum(rate(http_requests_total{code=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m]))"
    },
    "availability": {
      "ratio": 0.9977,
      "definition": "1 - (error_count / total_count)"
    },
    "throughput": {
      "mean_rps": 3.26,
      "p95_rps": 8.41,
      "stddev_rps": 2.14,
      "sample_count": 8640
    },
    "saturation": {
      "cpu_mean_ratio": 0.34,
      "cpu_p95_ratio": 0.72,
      "memory_mean_ratio": 0.61,
      "memory_p95_ratio": 0.78,
      "available": true
    }
  },
  "provenance": {
    "prometheus_endpoint": "https://thanos-querier.openshift-monitoring.svc:9091",
    "query_timestamps": {
      "start": "2024-12-16T10:30:00Z",
      "end": "2025-01-15T10:30:00Z"
    },
    "coverage_ratio": 0.97
  }
}
```

Each indicator includes a standard deviation (`stddev`) to support tolerance band derivation by downstream consumers (such as the drift detector). The `coverage_ratio` in provenance records the fraction of the lookback window with valid data.

### Proposal (LLM output, stage two)

Strict JSON validated against an embedded schema. For each proposed SLO it must include: the chosen SLI and its definition, the target, the error budget, the burn-rate alerting policy, and a rationale field that references the specific baseline values that justify the target. Reject and repair any proposal that fails schema validation (see the repair loop below). Reject any proposal whose numeric targets are not consistent with the provided baseline.

### Final outputs

1. OpenSLO YAML (the canonical, portable SLO spec).
2. Prometheus rules: recording rules plus multi-window, multi-burn-rate alerting rules derived from the error budget.
3. Audit bundle (JSON): evidence + baseline + proposal + rationale, plus a content hash of each section so the chain is verifiable.

## 9. LLM proposal stage requirements

- Use the OpenAI-compatible chat completions API at `LLM_BASE_URL` with model `LLM_MODEL`.
- Send the baseline artifact as evidence and require a JSON-only response conforming to the proposal schema. State explicitly in the system prompt that the model must only use numbers present in the baseline and must cite them in each rationale.
- Repair loop: if the response is not valid JSON or fails schema validation, send the validation error back and ask for a corrected response. Retry within the same conversation context: append the schema validation error as a user message and request correction. Do not start a new conversation. Keep the same temperature. Cap retries (for example 3), then fail with a clear error rather than emitting an invalid artifact.
- Consistency check in code after validation: confirm each proposed target is supported by the baseline (for example a p99 latency SLO target must not be tighter than the observed p99. If the LLM proposes a target tighter than the observed value, it must set a `requires_review` flag in the proposal and explain why in the rationale. The consistency check passes but the audit bundle marks the SLO for human review). Fail if the LLM invented a value not grounded in the baseline.

## 10. Red/green matrix and LLM eval rubric

### 10.1 Component matrix

Each component is governed by one discipline with explicit red and green criteria. `scripts/verify.sh` enforces the green column.

| Component | Discipline | Red (blocks the gate) | Green (passes the gate) |
|---|---|---|---|
| Prometheus query layer | TDD | errors, wrong labels, or empty result when data exists | returns expected series for fixtures, provenance captured |
| Baseline computation | TDD | any value deviates from the hand-computed fixture, or output is non-deterministic | exact match to fixtures, byte-for-byte reproducible |
| Artifact schemas and Go/Python boundary | CDD | any artifact fails its schema, or the two sides disagree on shape | all artifacts schema-valid on both sides, contract tests pass, baseline schema versioned |
| LLM proposal stage | EDD | any hard gate fails, or the rubric grid is below threshold | all hard gates green and rubric grid meets threshold across the eval suite |
| OpenSLO output | TDD + CDD | fails the OpenSLO schema | validates |
| Prometheus rules | TDD | `promtool check rules` fails | passes |
| Audit bundle | TDD + CDD | a section is missing or a content hash mismatches | complete, all hashes verify |
| End to end | all | any row above is red | `verify.sh` exits 0 |

### 10.2 LLM proposal eval rubric

The proposal stage is scored per eval case across these dimensions. Hard gates are mandatory: a single hard-gate failure is red regardless of the rest. Scored dimensions must meet the threshold for green.

Hard gates (mandatory):
- Schema validity: response validates against the proposal schema after at most the capped repair retries.
- Grounding: every numeric target cites a value present in the input baseline. No invented numbers.
- Consistency: no target is physically inconsistent with the baseline. A target tighter than the observed value is permitted only with a `requires_review` flag and an explicit rationale; the consistency check verifies this flag is present.

Scored dimensions:
- Indicator appropriateness: the selected SLIs are relevant to the service class implied by the evidence.
- Budget coherence: the error budget and the burn-rate alerting policy are internally consistent with the target.
- Rationale quality: each rationale references specific baseline values rather than generic prose.

Scoring mechanism: hard gates are scored programmatically (schema validation via the JSON schema library, grounding and consistency via numeric comparison against the baseline artifact). Scored dimensions use a heuristic check: indicator appropriateness passes if every indicator type present in the baseline has at least one corresponding SLI in the proposal; budget coherence passes if the error budget percentage and burn-rate windows are arithmetically consistent with the target; rationale quality passes if every rationale field contains at least one numeric value that appears in the baseline artifact. For prompt tuning (live mode), scored dimensions can alternatively use LLM-as-judge with a separate scoring prompt, but the hermetic CI mode must use deterministic heuristics only.

### 10.3 The eval grid

Run the rubric across every fixture in the eval suite to produce a cases-by-dimensions grid. Each cell is red or green. The suite is green only when every hard gate is green in every case and the scored dimensions meet the pass threshold (default: all scored dimensions green in every case). Record the grid as an artifact under `analysis/evals/` so prompt changes can be compared run to run. `verify.sh` fails if the grid is not green.

## 11. Build order (each milestone green before the next)

M1 (TDD + CDD). Freeze the evidence schema first. Write failing tests for the Prometheus query layer against recorded fixtures, then implement config resolution, the query client, and evidence collection. `--dry-run` emits a schema-valid evidence bundle for a real service. Verifiable without any LLM.

M2 (TDD). Write failing baseline tests with hand-computed expected values against `testdata/` fixtures, then implement the deterministic baseline computation. Same input always yields the same baseline artifact, byte-for-byte. Verifiable offline.

M3 (EDD + CDD). Freeze the proposal schema. Author the eval suite (fixtures plus rubric plus runner) before the stage exists. Then implement the LLM proposal stage with strict schema validation, the repair loop, and the baseline-consistency check, iterating until the eval grid is green. Verifiable hermetically against recorded model responses.

M4 (TDD + CDD). Freeze the output schema. Write failing renderer tests, then implement OpenSLO YAML, Prometheus recording and multi-window multi-burn-rate alerting rules, and the audit bundle with content hashes. Verifiable with `promtool check rules` and an OpenSLO schema check.

M5 (all). End-to-end wiring plus the verification script. A full `generate` run against fixtures produces all three outputs and a complete audit bundle, and `verify.sh` enforces the full component matrix and the eval grid.

Do not start a milestone until the previous one is green by its discipline.

## 12. Coding standards

- Small, single-purpose functions. Clear error messages that name the cause.
- All artifacts validated against embedded JSON schemas at every boundary. Schemas are the single source of truth, shared between Go and Python.
- Deterministic stage one: no randomness, no network beyond the Prometheus query, reproducible output.
- Secrets only from environment. Never log or persist `LLM_API_KEY` or `PROM_TOKEN`.
- Tests first for deterministic code, contracts first for boundaries, evals first for the LLM stage.
- Do not use em dashes in code comments, docs, or generated output.
- For byte-for-byte reproducibility, serialize all JSON artifacts with sorted keys, 2-space indentation, and a fixed decimal format for floats (6 significant digits, no trailing zeros). Define the canonical serialization once as a shared utility and reuse it in both Go and Python.
- `analysis/schemas/` is the single source of truth for all JSON schemas. The Go binary embeds them from this path via `go:embed`.

## 13. Preflight script

Create `scripts/preflight.sh` that checks: Go and Python versions present, dependencies installed, `PROM_URL` set and reachable, `LLM_BASE_URL` set and reachable (a cheap models or health call), and required tools present (`promtool`). Print a clear pass/fail line per check. Exit non-zero on any failure.

## 14. Verification (exit 0 only on full success)

Create `scripts/verify.sh` that runs hermetically (using `testdata/` and `analysis/evals/` fixtures, no live cluster or live model needed) and:

1. Runs Go and Python unit tests.
2. Runs the contract tests for every artifact boundary, including the frozen baseline schema.
3. Runs the LLM eval grid against recorded responses and asserts it is green at threshold.
4. Runs a full `generate` against recorded fixtures.
5. Asserts the OpenSLO output validates against the OpenSLO JSON Schema using a YAML-to-JSON conversion plus a JSON Schema validator, since no standalone OpenSLO validation tool exists.
6. Runs `promtool check rules` on the generated Prometheus rules and asserts it passes.
7. Asserts the audit bundle contains all three sections (evidence, baseline, proposal) and that its content hashes verify.
8. Asserts every proposed target is consistent with the baseline (the consistency check from section 9).

Print a summary that maps to the component matrix in section 10.1. Exit 0 only if every row is green. Exit non-zero otherwise. This script is the definition of done.

## 15. Done criteria and handoff

Done when: `scripts/preflight.sh` and `scripts/verify.sh` both exist and pass, the component matrix and the eval grid are fully green, `sloscope generate --dry-run` works with no LLM credentials, a full run produces valid OpenSLO plus Prometheus rules plus a complete audit bundle, and the baseline artifact is a versioned, stable contract.

Handoff note for the next phase: the versioned baseline artifact is the reference input for a future drift detector. Keep its schema stable. The drift phase will measure live indicators against this baseline and classify deviation, reusing the same evidence, contract, and eval patterns established here.
