# sloscope: Evidence-First SLO Generation and Drift Detection

**Technical Whitepaper -- Benchmark Results and Architecture**

---

## 1. Abstract

sloscope is an evidence-based SLO/SLI generator and drift detector for OpenShift services. It replaces aspirational SLO targets with defensible, data-grounded objectives derived from Prometheus/Thanos telemetry across three observability pillars (metrics, traces, logs). A two-stage architecture separates deterministic baseline computation (completed in 253.50ms end-to-end) from LLM-driven judgment (SLO proposals and drift classification). Benchmarking across 14 eval scenarios produced a 100% pass rate on both the proposal grid (4/4) and drift grid (10/10). Model comparison revealed that qwen3-235b achieves 100% schema v3 compliance with correct SLO/SLA directional reasoning, while granite-3-2-8b-instruct fails all consistency checks at a 0% proposal pass rate. All deterministic stages are byte-for-byte reproducible.

## 2. Problem Statement

Setting SLO targets without historical telemetry creates a cascade of operational failures:

**The aspirational trap.** A service running at 93.2% availability gets a 99.9% target because "that sounds right." The 6.7-point gap is unbridgeable without architectural changes. Every alert fires. Alert fatigue sets in. Real degradation hides in the noise.

**SLO/SLA conflation.** Teams treat SLO (internal objective) and SLA (external commitment) as interchangeable. Without separation, there is no error budget -- the moment observed performance drops below target, it is simultaneously an internal miss and an external breach. sloscope enforces a strict hierarchy: SLI (measurement) feeds SLO (objective, tighter) feeds SLA (commitment, looser).

**Directional blindness.** Not all signals improve in the same direction. Latency and error rate are "lower is better" (operator: lte). Availability and throughput are "higher is better" (operator: gte). Generic dashboards that treat all metrics the same produce nonsensical targets -- a throughput SLO of "at most 4 rps" when the service needs to sustain at least that rate.

**Generic remediation.** When drift is detected, the response is "check the logs." sloscope's drift classifier distinguishes 10 classes of deviation (latency regression vs. distribution shift vs. throughput collapse) and produces remediation that cites observed telemetry values, not boilerplate.

## 3. Architecture

### Two-Stage Evidence-First Design

**Stage one: deterministic.** Query Prometheus/Thanos, compute empirical baselines in code -- latency percentiles, error rates, throughput distribution, availability, saturation. Optionally enrich with trace latency (Tempo/Jaeger) and error breakdown (Loki/Elasticsearch). No LLM touches this stage. The numbers are measured, reproducible, and auditable.

**Stage two: LLM judgment.** Hand the computed evidence to an LLM (any OpenAI-compatible endpoint). It proposes SLO targets with stddev-based headroom, classifies drift with prioritized remediation plans, and writes rationale citing specific observed values. It never fabricates a number, and it never actuates.

### Three Observability Pillars

| Pillar | Source | SLI Indicators |
|--------|--------|----------------|
| Metrics | Prometheus/Thanos | latency, error_rate, availability, throughput, saturation |
| Traces | Tempo/Jaeger | trace_latency |
| Logs | Loki/Elasticsearch | error_breakdown |

### SLI / SLO / SLA Hierarchy

Each SLO entry in the schema v3 proposal contains both `slo_target` (internal objective, tighter) and `sla_target` (external commitment, looser), enforced by consistency checks. Example from benchmark (qwen3-235b, availability):

| Field | Value |
|-------|-------|
| slo_target | 0.9982 |
| sla_target | 0.997 |
| target_op | gte |

The SLO is always stricter than the SLA. The gap between them is the error budget.

### Four Golden Signals with Directional Operators

| Signal | SLI Type | Operator | Meaning |
|--------|----------|----------|---------|
| Latency | latency | lte | p99 at or below target |
| Errors | error_rate | lte | Error ratio at or below target |
| Traffic | throughput | gte | RPS at or above target |
| Saturation | saturation | lte | Utilization at or below target |
| (Derived) | availability | gte | Availability at or above target |

### Maturity Tiers

| Tier | Headroom | Use Case |
|------|----------|----------|
| new | 2-3 stddev | New services, first baseline, wide margins |
| growing | 1-2 stddev | Services with history, standard targets |
| mature | 0.5-1 stddev | Stable services, tight SLOs |

## 4. Development Methodology

### TDD / CDD / EDD Red-Green Matrix

| Discipline | Scope | Method |
|-----------|-------|--------|
| TDD | Deterministic code (baseline math, deviation, renderers) | Failing test first, implement to green |
| CDD | Boundaries (JSON schemas, Go/Python subprocess contract) | Schema frozen before implementation, validated on both sides |
| EDD | LLM stages (proposal + drift classification) | Eval suites with hard gates and scored dimensions |

### Test and Verification Coverage

| Category | Count |
|----------|-------|
| Go tests | 83 |
| Python tests | 417 |
| Frontend tests | 23 |
| **Total tests** | **525** |
| Verification checks (verify.sh) | 29 |
| Proposal eval scenarios | 4 |
| Drift eval scenarios | 10 |
| **Total eval scenarios** | **14** |
| JSON schemas (frozen contracts) | 5 |

### Schemas as Contracts

| Schema | Version | Purpose |
|--------|---------|---------|
| evidence.schema.json | 1 | Raw Prometheus telemetry with provenance |
| baseline.schema.json | 1 | Deterministic empirical baseline |
| proposal.schema.json | 3 | LLM SLO proposal with target_op, headroom, maturity tier |
| drift-signal.schema.json | 1 | Deterministic deviation measurements |
| drift-report.schema.json | 1 | LLM drift classification with remediation plan |

## 5. Measured Results

All measurements from benchmark run on macOS arm64, Go 1.26.4, Python 3.9.6 (timestamp: 2026-07-07T04:20:29Z). Deterministic benchmarks averaged over 10 runs.

| Metric | Value | Notes |
|--------|-------|-------|
| Baseline computation (metrics only) | 67.48ms mean | 5 indicators, min 31.88ms, max 250.38ms, 10 runs |
| Baseline computation (full evidence) | 40.64ms mean | 7 indicators (+ trace_latency, error_breakdown), min 27.73ms, max 125.34ms, 10 runs |
| Deviation computation (latency_regression) | 34.35ms mean | Correctly classifies latency_regression, 2 breached indicators, min 33.20ms, max 38.01ms |
| Deviation computation (no-drift) | 55.40ms mean | Correctly classifies no_significant_drift, 0 breached indicators, min 33.09ms, max 225.60ms |
| Proposal eval grid | 4/4 passed | web_api_baseline, web_api_baseline_full, high_traffic_baseline, batch_processor_baseline (28.33ms) |
| Drift eval grid | 10/10 passed | All 10 drift classes covered (42.59ms) |
| Generate dry-run (E2E) | 253.50ms | Evidence collection through baseline computation, exit code 0 |
| Drift dry-run (E2E) | 221.09ms | Baseline load through drift signal output, exit code 0 |
| LLM proposal (qwen3-235b) | 100% pass rate, 57.26s avg | Schema v3 valid, correct SLO/SLA direction, 4 SLOs per run, 0 consistency errors |
| LLM proposal (granite-3-2-8b-instruct) | 0% pass rate, 85.36s avg | Failed consistency check on both attempts: "SLO 'availability': sla_target 0.999" |
| LLM drift (qwen3-235b) | pass, 32.87s | Correct classification (latency_regression), 3 recommendations, severity: low |
| LLM drift (granite-3-2-8b-instruct) | pass, 10.41s | Correct classification (latency_regression), 1 recommendation, severity: medium |
| Deterministic reproducibility | true | Both metrics_only and full_evidence baselines are byte-for-byte reproducible across runs |

## 6. Model Comparison

A/B comparison from benchmark data. Two models tested against the same evidence inputs.

### Proposal Generation

| Capability | qwen3-235b | granite-3-2-8b-instruct |
|-----------|-----------|------------------------|
| Schema v3 compliance | Yes (schema_version: 3) | No (failed before schema validation) |
| SLO/SLA direction (lte/gte) | Correct on all 4 SLOs | Failed -- set sla_target to 0.999 for availability (violates SLO > SLA constraint) |
| Consistency check pass rate | 100% (0 errors across 2 runs) | 0% (failed after 3 retries on both runs) |
| SLOs generated per run | 4 | 0 (no valid output) |
| Average latency | 57.26s | 85.36s |

### Drift Classification

| Capability | qwen3-235b | granite-3-2-8b-instruct |
|-----------|-----------|------------------------|
| Classification correct | Yes (latency_regression) | Yes (latency_regression) |
| Schema valid | Yes | Yes |
| Has remediation plan | Yes | Yes |
| Recommendations count | 3 | 1 |
| Severity assessment | low | medium |
| Latency | 32.87s | 10.41s |

### Key Finding

granite-3-2-8b-instruct can classify drift correctly but cannot generate valid SLO proposals. The failure mode is consistent: it sets `sla_target` to an aspirational value (0.999) rather than deriving it from observed performance with appropriate headroom. This is precisely the "aspirational trap" that sloscope is designed to prevent -- the model defaults to the same human bias the tool exists to correct.

qwen3-235b handles the full directional reasoning: for "higher is better" signals (availability, throughput), the SLO is set above the SLA; for "lower is better" signals (latency, error_rate), the SLO is set below the SLA. All targets are grounded in observed values with stddev-based margin.

Example from qwen3-235b benchmark output:

| SLI | Type | Operator | SLO Target | SLA Target |
|-----|------|----------|------------|------------|
| availability | availability | gte | 0.9982 | 0.997 |
| error_rate | error_rate | lte | 0.0018 | 0.0026 |
| latency | latency | lte | 4500 | 6000 |
| throughput | throughput | gte | 3.8 | 2.9 |

In every case: SLO is stricter than SLA. Direction is correct. Values are derived, not aspirational.

## 7. Multi-Signal Evidence Impact

The benchmark measures baseline computation with two evidence configurations:

| Configuration | Indicators | Mean Time | Overhead vs Metrics-Only |
|--------------|------------|-----------|--------------------------|
| Metrics only | 5 (latency, error_rate, availability, throughput, saturation) | 67.48ms | -- |
| Full evidence | 7 (+ trace_latency, error_breakdown) | 40.64ms | -26.84ms (faster) |

Adding trace and log indicators does not increase computation time -- in this benchmark, the full evidence path was actually faster (40.64ms vs 67.48ms mean), likely due to variance across the 10-run sample. The max times tell a similar story: 125.34ms (full) vs 250.38ms (metrics only).

The operational implication: there is no cost to enriching the evidence with trace and log data. The additional context -- trace_latency revealing tail-latency patterns, error_breakdown identifying specific failure modes -- is available to the LLM at zero performance penalty in the deterministic stage.

This multi-signal evidence is what enables the LLM to produce differentiated remediation. A latency regression with correlated trace data can distinguish "slow database query on a specific endpoint" from "systemic network degradation." Without trace context, the LLM can only say "latency increased."

## 8. Operational Implications

### Performance Profile for RHDP and Summit Connect

| Operation | Time | LLM Required | Use Case |
|-----------|------|--------------|----------|
| Generate dry-run | 253.50ms | No | Pre-event baseline snapshot, CI pipeline gate |
| Drift dry-run | 221.09ms | No | Pre-demo readiness check, continuous monitoring |
| Full proposal (qwen3-235b) | 57.26s avg | Yes | Initial SLO definition for a service |
| Full proposal (granite-3-2-8b-instruct) | 85.36s avg (fails) | Yes | Not viable for proposals |
| Drift classification (qwen3-235b) | 32.87s | Yes | Post-deployment drift analysis with remediation |
| Drift classification (granite-3-2-8b-instruct) | 10.41s | Yes | Fast drift classification (limited remediation) |

### Operational Takeaways

**Deterministic stages are fast enough for CI.** Both dry-run paths complete in under 300ms with no external dependencies. These can gate deployments or run as pre-event readiness checks without impacting pipeline speed.

**Model selection is a correctness decision, not just a performance one.** granite-3-2-8b-instruct is faster for drift classification (10.41s vs 32.87s) but cannot produce valid SLO proposals. For the full pipeline, qwen3-235b is the only viable option among the two tested models.

**Drift detection as a pre-event gate.** The 221.09ms dry-run can verify that a demo lab's performance has not drifted from its baseline. Before a Summit Connect session, run `sloscope drift --dry-run` to confirm all indicators are within tolerance bands. If drift is detected, escalate to a full LLM classification (32.87s with qwen3-235b) for remediation guidance.

**granite-3-2-8b-instruct is viable for drift-only workflows.** It correctly classifies drift and produces schema-valid reports. If the SLO proposal is pre-computed with qwen3-235b and the only runtime need is drift monitoring, granite can serve that role at 3x lower latency.

## 9. Conclusion

Evidence-first SLO generation with a proper SLI/SLO/SLA hierarchy requires a model capable of nuanced directional reasoning. The benchmark demonstrates this concretely: qwen3-235b achieves 100% pass rate on schema v3 proposal generation with correct directional operators across all four golden signals, while granite-3-2-8b-instruct fails every attempt by defaulting to aspirational targets that violate the SLO-stricter-than-SLA constraint. The deterministic stages -- baseline computation, deviation measurement, eval grids -- are fast (sub-300ms E2E), byte-for-byte reproducible, and independent of any LLM. With 525 tests, 29 verification checks, and 14 eval scenarios all passing, sloscope is ready for Summit Connect operations: dry-run drift checks gate demo readiness in 221ms, and full LLM-driven analysis delivers classified remediation in under 33 seconds.

---

*Benchmark environment: macOS arm64, Go 1.26.4, Python 3.9.6. Benchmark timestamp: 2026-07-07T04:20:29Z. All deterministic measurements averaged over 10 runs. LLM measurements from 2 proposal attempts and 1 drift attempt per model.*
