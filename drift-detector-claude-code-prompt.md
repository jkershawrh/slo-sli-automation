# Claude Code Build Prompt: Evidence-Based Drift Detector and Remediation

Doc 2 of 2. This document builds the drift detector and remediation layer on top of Doc 1. It consumes the versioned baseline artifact produced by Doc 1 as a frozen input contract and extends the same CLI with a `drift` subcommand. Paste this whole document into Claude Code (`claude`) from the root of the same working directory that Doc 1 produced. It is self-contained but assumes Doc 1 is built and green.

---

## 1. Role and objective

You are a senior platform engineer extending an existing evidence-based SLO tool with drift detection and remediation.

Given a reference baseline (the versioned artifact produced by Doc 1), the tool samples live telemetry from Prometheus/Thanos, computes the same indicators over an evaluation window, and measures deviation from the baseline deterministically. It then uses an LLM to classify the drift, assess severity, and produce evidence-based remediation recommendations, each justified by the deterministic drift signals it was given.

Detection and measurement are deterministic and auditable. The LLM classifies and recommends. It never invents a number and never actuates. Remediation output is a recommendation for a human, not an action.

## 2. Core philosophy (do not violate)

Two stages, evidence first. This mirrors Doc 1 exactly, applied to drift.

Stage one is deterministic. Sample the live indicators over an evaluation window, recompute them exactly as Doc 1 computed the baseline, and measure deviation against the baseline reference using tolerance bands derived from the baseline. Produce a drift-signal artifact: per indicator, the live value, the baseline value, the deviation, the direction, and whether it breached its band. A first-pass drift class is assigned by rule from the dominant signal. All of this is measured, reproducible, and auditable. No LLM touches this stage.

Stage two is judgment. Hand the drift-signal artifact to the LLM as evidence. Its job is to confirm or refine the classification, assess severity, reason about likely cause, and recommend remediation, with a rationale that cites the specific drift signals and baseline values it was given. It must select and justify. It must never invent a metric value, and it must never emit an action to be executed automatically.

Auditability is a first-class requirement. The output always includes an audit bundle: the baseline reference, the live evidence, the deterministic drift signals, and the LLM classification and remediation with rationale, so the chain from observed deviation to recommended response is fully traceable. This reuses Doc 1's audit patterns.

## 3. Development methodology (TDD, CDD, EDD)

Same three disciplines as Doc 1. Tests, contracts, or evals first, then implementation.

TDD (Test-Driven Development) governs the deterministic code: live sampling, deviation math, band-breach logic, the rule-based first-pass classifier, and the report and audit renderers. Failing test first, then green, then refactor. For deviation and classification, hand-label small fixtures with known expected drift signals and classes and assert exact, reproducible results before implementing.

CDD (Contract-Driven Development) governs the boundaries. The baseline artifact is a frozen input contract owned by Doc 1: validate every incoming baseline against Doc 1's versioned schema and refuse to run on a version you do not support. The drift-signal artifact, the drift report, and the audit bundle each get their own schema, written and frozen before the code that produces them, validated on both the Go and Python sides.

EDD (Eval-Driven Development) governs the LLM classification and remediation stage. Build a labeled eval suite: drift scenarios with known ground-truth class, expected severity band, and expected remediation category. Develop the prompt and the stage against the suite until the eval grid is green. Runs hermetically in CI against recorded model responses, and live against the endpoint for tuning.

## 4. Non-goals for this version

- No automatic remediation or actuation. The tool recommends; a human decides and acts. Do not wire the recommendation to any execution path.
- No SLO generation. That is Doc 1. This document consumes the baseline, it does not regenerate it.
- No web dashboard.
- No Datadog adapter. Prometheus/Thanos only.
- Do not hardcode any single model vendor. OpenAI-compatible base URL and key, as in Doc 1.

## 5. Read before you write any code

1. Read Doc 1's baseline artifact schema first and treat it as a frozen input contract. Record which schema versions you support. Do not modify Doc 1's schema.
2. Read the existing repo from Doc 1 fully. Reuse its config resolution, Prometheus client, schema validation, and audit bundle code. Extend the CLI with a `drift` subcommand rather than building a new tool. Report what you are reusing before proceeding.
3. Confirm environment access. Print the resolved Prometheus/Thanos URL and model endpoint base URL (not secrets). If either is unset, stop and say so.
4. Load one real baseline artifact and sample the same service live for a small window. Print the live values next to the baseline values so you confirm the indicators line up before writing the deviation layer. If live Prometheus access is unavailable, use recorded fixtures from `testdata/` instead. The live confirmation is recommended but not blocking.

5. Run `scripts/verify.sh` and confirm Doc 1's checks are green before proceeding. If any Doc 1 check is red, fix it first.

Report findings from these steps, then continue.

## 6. Environment and toolchain

Same as Doc 1: OpenShift, Prometheus/Thanos, OpenAI-compatible LLM endpoint, Go 1.22+ core, Python 3.11+ analysis, secrets from environment only.

Environment variables (same set as Doc 1): `PROM_URL`, `PROM_TOKEN`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`.

Additional input: the path to a baseline artifact produced by Doc 1, passed on the command line.

## 7. Architecture

Go core owns: the `drift` subcommand and its UX, loading and validating the incoming baseline against Doc 1's schema, live sampling via the reused Prometheus client, orchestration of the two stages, schema validation of every artifact, and rendering of the drift report and audit bundle.

Python analysis owns: deterministic deviation computation and rule-based first-pass classification from an evidence bundle plus the baseline, and the LLM stage that reads the drift-signal artifact and returns a schema-valid classification and remediation.

If any reused component is too tightly coupled to the generate flow (for example hardcoded section names in the audit bundle, or a Prometheus client that assumes lookback semantics), refactor it into a generic form as part of M1 before adding drift-specific code.

The Go to Python boundary is a subprocess call. Go invokes Python by script path (for example `python3 analysis/deviation.py` for stage one, `python3 analysis/classify.py` for stage two). Stage one receives both the live evidence bundle and the relevant baseline values as a combined JSON payload on stdin. The result JSON is read from stdout. Stderr carries log lines and error messages but is not parsed as structured data. Exit 0 means success with valid JSON on stdout. Non-zero exit means failure with a diagnostic on stderr. Go enforces a configurable timeout per subprocess call (default 60 seconds). Contracts are validated on both sides.

Full repo layout after Doc 2 (new and extended items marked):

```
.
  cmd/sloscope/                          Go CLI entrypoint (extended: add drift subcommand)
  internal/config/                       env config resolution (reused from Doc 1)
  internal/prom/                         Prometheus/Thanos client and queries (reused from Doc 1)
  internal/pipeline/                     orchestration, subprocess boundary (extended: generalize for drift stages)
  internal/render/                       OpenSLO + Prometheus rules + audit bundle (extended: drift report render)
  internal/schema/                       embedded JSON schemas + validation (extended: drift schemas)
  internal/drift/                        [NEW] baseline load + validate, live sampling orchestration
  analysis/
    baseline.py                          deterministic baseline computation (Doc 1)
    propose.py                           LLM proposal stage (Doc 1)
    deviation.py                         [NEW] deterministic deviation + rule-based first-pass class
    classify.py                          [NEW] LLM classification + remediation stage
    schemas/                             JSON schemas (extended: add drift-signal, drift-report schemas)
    evals/                               eval fixtures + rubric + runner (extended: add labeled drift scenarios)
    tests/                               pytest fixtures + unit tests (extended: add deviation + classifier tests)
  scripts/
    preflight.sh                         (extended: drift-specific checks)
    verify.sh                            (extended: drift verification)
  testdata/                              recorded Prometheus and LLM responses (extended: drift fixtures)
  Makefile
  README.md
```

## 8. Interface contracts

### CLI

```
sloscope drift \
  --service checkout-api \
  --baseline ./out/checkout-api/baseline.json \
  --window 1h \
  --out ./out/checkout-api/drift

sloscope drift --service checkout-api --baseline ./out/checkout-api/baseline.json --window 1h --dry-run
```

`--dry-run` runs live sampling and the deterministic deviation and first-pass classification, prints the drift-signal artifact, and does not call the LLM. Must work with no LLM credentials present.

Exit codes: 0 on success (whether or not drift was found), non-zero on failure (unreachable Prometheus, unsupported baseline version, schema-invalid artifact, LLM failure, render failure). Whether drift was detected is reported in the output, not signaled through the exit code.

### Baseline artifact (frozen input, owned by Doc 1)

Validate against Doc 1's versioned schema on load. Refuse unsupported versions with a clear error. This is the reference the deviation stage measures against.

### Live evidence bundle (Go to Python, stage one input)

The live indicator samples over the evaluation window, with provenance: query strings, timestamps, endpoint. Carried into the audit bundle unchanged. Note: short evaluation windows compared against long-lookback baselines may show apparent drift due to time-of-day or day-of-week effects. The evaluation window duration and any time-alignment caveats are recorded in the audit bundle. Emit a warning if the baseline artifact timestamp is older than a configurable threshold (default 90 days). If an indicator from the baseline is unavailable in the live sample (for example saturation metrics not present for the service), mark it as `skipped` in the drift-signal artifact with a reason field. If overall data coverage across all indicators is below 50%, fail with an error. If below 90%, emit a warning.

### Tolerance bands

Tolerance bands are owned by the drift detector, not the baseline. Default bands are derived from the baseline's per-indicator standard deviation (for example, baseline value plus or minus 2 standard deviations). Bands can be overridden via a `--tolerance` config flag or a tolerance configuration file. Each band and its derivation method are recorded in the audit bundle as an explicit governance decision.

### Drift-signal artifact (deterministic, stage one output)

Versioned. Per indicator: live value, baseline value, absolute and relative deviation, direction, band-breach boolean, and the rule-based first-pass drift class. Plus an overall dominant-signal summary: the dominant signal is the indicator with the largest normalized breach magnitude (absolute deviation divided by the band width). All breached indicators are listed in the artifact; the dominant signal determines the rule-based first-pass class. No prose, no recommendations, just measured deviation. This is the evidence the LLM stage reasons over.

Example drift-signal artifact structure:

```json
{
  "schema_version": 1,
  "service": "checkout-api",
  "evaluation_window": "1h",
  "evaluated_at": "2025-01-16T14:00:00Z",
  "baseline_schema_version": 1,
  "indicators": [
    {
      "name": "latency_p99_ms",
      "live_value": 587.3,
      "baseline_value": 412.1,
      "abs_deviation": 175.2,
      "rel_deviation": 0.425,
      "direction": "increasing",
      "band_upper": 586.5,
      "band_lower": 237.7,
      "band_breach": true,
      "first_pass_class": "latency_regression"
    },
    {
      "name": "error_rate_ratio",
      "live_value": 0.0031,
      "baseline_value": 0.0023,
      "abs_deviation": 0.0008,
      "rel_deviation": 0.348,
      "direction": "increasing",
      "band_upper": 0.0039,
      "band_lower": 0.0007,
      "band_breach": false,
      "first_pass_class": "no_significant_drift"
    }
  ],
  "dominant_signal": {
    "indicator": "latency_p99_ms",
    "class": "latency_regression",
    "breach_magnitude": 1.003
  },
  "all_breached_indicators": ["latency_p99_ms"],
  "provenance": {
    "prometheus_endpoint": "https://thanos-querier.openshift-monitoring.svc:9091",
    "query_timestamps": {
      "start": "2025-01-16T13:00:00Z",
      "end": "2025-01-16T14:00:00Z"
    },
    "coverage_ratio": 0.98
  }
}
```

### Edge cases

For relative deviation when the baseline value is near zero, use a stabilized formula: `(live - baseline) / max(baseline, epsilon)` where epsilon is a small constant appropriate to the indicator type (for example 0.001 for ratios, 1.0 for milliseconds). This prevents infinite relative deviations on low-error-rate services.

### Drift report (LLM output, stage two)

Strict JSON validated against an embedded schema. Contains: the confirmed or refined drift classification (from a fixed taxonomy), a severity, likely-cause reasoning, and one or more remediation recommendations. Each recommendation includes a recommended action, a confidence, and a rationale that cites the specific drift signals and baseline values that justify it. No invented numbers. No auto-executable action payloads.

Drift taxonomy (fixed set, extend deliberately): latency regression, latency improvement, error-rate elevation, error-rate reduction, throughput collapse, throughput surge, saturation approach, availability drop, distribution shift, no significant drift. The taxonomy is a schema-level enum in the drift-report schema. Adding a taxonomy entry requires a schema version bump.

### Final outputs

1. Drift report (the classified incident with remediation recommendations) as JSON and a human-readable summary.
2. Optional Prometheus alert annotations derived from the classification, for teams that want the drift surfaced through existing alerting. Off by default.
3. Audit bundle (JSON): baseline reference + live evidence + drift signals + drift report + rationale, each section content-hashed, reusing Doc 1's audit format.

## 9. LLM classification and remediation stage requirements

- Use the OpenAI-compatible chat completions API at `LLM_BASE_URL` with model `LLM_MODEL`.
- Send the drift-signal artifact (and the relevant baseline values) as evidence and require a JSON-only response conforming to the drift-report schema. State explicitly in the system prompt that the model must only use numbers present in the drift signals or baseline, must cite them, must choose a class from the fixed taxonomy, and must not emit an executable action.
- Repair loop: on invalid JSON or schema failure, send the validation error back for correction, capped (for example 3), then fail cleanly rather than emit an invalid artifact.
- Consistency checks in code after validation: the chosen class must be consistent with the dominant deterministic signal; the severity must be consistent with the magnitude of deviation; every cited number must exist in the drift signals or baseline. Fail on any invented value or a class that contradicts the signals.

## 10. Red/green matrix and LLM eval rubric

### 10.1 Component matrix

`scripts/verify.sh` enforces the green column.

| Component | Discipline | Red (blocks the gate) | Green (passes the gate) |
|---|---|---|---|
| Baseline load and validate | CDD | accepts an unsupported or malformed baseline, or fails a valid one | validates against Doc 1's versioned schema, rejects unsupported versions cleanly |
| Live sampling | TDD | errors, wrong labels, or empty result when data exists | returns expected series for fixtures, provenance captured |
| Deviation computation | TDD | any value deviates from the hand-labeled fixture, or output is non-deterministic | exact match to fixtures, byte-for-byte reproducible |
| Rule-based first-pass class | TDD | misclassifies a labeled fixture | matches the labeled class for every deterministic fixture |
| Drift-signal and report schemas, boundary | CDD | any artifact fails its schema, or the two sides disagree on shape | all artifacts schema-valid on both sides, contract tests pass, artifacts versioned |
| LLM classification and remediation | EDD | any hard gate fails, or the eval grid is below threshold | all hard gates green and the eval grid meets threshold across the labeled suite |
| Audit bundle | TDD + CDD | a section is missing or a content hash mismatches | complete, all hashes verify |
| End to end | all | any row above is red | `verify.sh` exits 0 |

### 10.2 LLM classification and remediation eval rubric

Scored per labeled eval case. Hard gates are mandatory; a single hard-gate failure is red. Scored dimensions must meet the threshold for green.

Hard gates (mandatory):
- Schema validity: validates against the drift-report schema after at most the capped retries.
- Grounding: every cited number exists in the drift signals or baseline. No invented numbers.
- Class validity and consistency: the class is from the fixed taxonomy and is consistent with the dominant deterministic signal.
- No actuation: the output contains no executable action payload. Detect by pattern-matching the remediation text against executable content: shell commands (`kubectl`, `oc`, `curl`, `docker`, `helm`), YAML or JSON code blocks, API call patterns. Reject any response containing these patterns and send to the repair loop.

Scored dimensions:
- Classification accuracy: the confirmed class matches the known injected drift type for the fixture.
- Severity calibration: the severity aligns with the magnitude of deviation in the signals.
- Remediation relevance: the recommended action is appropriate to the classified drift type.
- Rationale quality: each rationale cites specific drift signals or baseline values rather than generic prose.

Scoring mechanism: hard gates are scored programmatically (schema validation via the JSON schema library, grounding via numeric comparison against the drift-signal artifact and baseline, class validity via enum membership check, no-actuation via pattern matching). Scored dimensions use deterministic heuristics for hermetic CI: classification accuracy passes if the confirmed class matches the ground-truth label for the fixture; severity calibration passes if the severity falls within the expected range for the fixture's deviation magnitude; remediation relevance passes if the recommended action category matches the expected category for the drift type; rationale quality passes if every rationale field contains at least one numeric value present in the drift signals or baseline. For prompt tuning (live mode), scored dimensions can alternatively use LLM-as-judge with a separate scoring prompt.

### 10.3 The eval grid

Build the eval suite from labeled drift scenarios: inject a known drift type into a baseline-plus-live fixture, one per taxonomy member (latency regression, latency improvement, error-rate elevation, error-rate reduction, throughput collapse, throughput surge, saturation approach, availability drop, distribution shift) plus a no-drift control, each with a ground-truth class, expected severity band, and expected remediation category. Eval fixtures are hand-crafted JSON pairs (baseline plus live evidence) with known deviations. The minimum eval suite requires one scenario per taxonomy member plus the no-drift control (11 scenarios minimum). Run the rubric across every scenario to produce a cases-by-dimensions grid. The suite is green only when every hard gate is green in every case and all scored dimensions are green in every case. Record the grid under `analysis/evals/` so prompt changes are measurable run to run. `verify.sh` fails if the grid is not green.

## 11. Build order (each milestone green before the next)

M1 (CDD + TDD). Add the `drift` subcommand. Validate the incoming baseline against Doc 1's frozen schema, rejecting unsupported versions. Write failing tests for live sampling against recorded fixtures, then implement sampling and the live evidence bundle. `--dry-run` runs without an LLM.

M2 (TDD). Freeze the drift-signal schema. Write failing tests with hand-labeled expected deviations and first-pass classes, then implement deterministic deviation, band-breach logic, and the rule-based classifier. Reproducible byte-for-byte.

M3 (EDD + CDD). Freeze the drift-report schema. Author the labeled eval suite and rubric before the stage exists. Implement the LLM classification and remediation stage with strict schema validation, the repair loop, and the consistency checks, iterating until the eval grid is green.

M4 (TDD + CDD). Render the drift report (JSON plus human-readable summary), the optional Prometheus alert annotations, and the audit bundle reusing Doc 1's format with content hashes. Verifiable against schema checks.

M5 (all). End-to-end wiring plus verification. A full `drift` run against fixtures produces the drift report and a complete audit bundle, and `verify.sh` enforces the full component matrix and the eval grid.

Do not start a milestone until the previous one is green by its discipline.

## 12. Coding standards

Same as Doc 1. Small single-purpose functions, clear errors, schema validation at every boundary, deterministic stage one, secrets only from environment, tests first for deterministic code, contracts first for boundaries, evals first for the LLM stage, no em dashes in comments, docs, or generated output. Reuse Doc 1 code rather than duplicating it. For byte-for-byte reproducibility, serialize all JSON artifacts with sorted keys, 2-space indentation, and a fixed decimal format for floats (6 significant digits, no trailing zeros), reusing the canonical serialization utility from Doc 1.

## 13. Preflight script

Add a drift-specific check block to `scripts/preflight.sh` that verifies: Go and Python present, dependencies installed, `PROM_URL` reachable, `LLM_BASE_URL` reachable, `promtool` present, and that a sample baseline artifact validates against Doc 1's schema. Clear pass/fail per check, non-zero exit on any failure.

## 14. Verification (exit 0 only on full success)

Extend `scripts/verify.sh` to run hermetically and, in addition to Doc 1's checks:

1. Runs the new Go and Python unit tests (deviation, first-pass classifier, sampling).
2. Runs the contract tests: baseline load against Doc 1's schema (including a rejected unsupported version), and the drift-signal and drift-report schemas.
3. Runs the labeled LLM eval grid against recorded responses and asserts it is green at threshold.
4. Runs a full `drift` against recorded fixtures for a drift case and a no-drift control.
5. Asserts the drift report validates and its classification is consistent with the deterministic signals.
6. Asserts the audit bundle contains all sections (baseline reference, live evidence, drift signals, drift report) and that content hashes verify.

Print a summary mapping to the component matrix in section 10.1. Exit 0 only if every row is green. This script is the definition of done for Doc 2. Guard drift checks behind a presence check (for example `if [ -d internal/drift ]`) so that verify.sh remains green for Doc 1-only builds.

## 15. Done criteria and handoff

Done when: the `drift` subcommand loads and validates a Doc 1 baseline, the component matrix and eval grid are fully green, `sloscope drift --dry-run` works with no LLM credentials, a full run produces a classified drift report with grounded remediation recommendations plus a complete audit bundle, and the tool never actuates.

Handoff note for a future phase: remediation is recommendation-only here by design. A later closed-loop phase could add a human-approval gate and a constrained actuation path, sensing through this drift report, deciding with the recommendation, acting under policy, and verifying against a fresh drift run. That phase inherits every contract, eval, and audit pattern established across Doc 1 and Doc 2.
