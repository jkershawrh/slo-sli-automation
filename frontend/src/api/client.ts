// API client with timing, matching the DeepField pattern

export interface ApiCall<T> {
  request: { method: string; path: string; body?: unknown }
  response: { status: number; data: T }
  elapsed: number
}

async function request<T>(method: string, path: string, body?: unknown): Promise<ApiCall<T>> {
  const start = performance.now()
  const opts: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body) opts.body = JSON.stringify(body)

  const res = await fetch(path, opts)
  const data = await res.json()
  const elapsed = performance.now() - start

  if (!res.ok) {
    throw new Error(data.detail || `API error: ${res.status}`)
  }

  return {
    request: { method, path, body },
    response: { status: res.status, data },
    elapsed,
  }
}

// --- Types matching JSON schemas ---

// Evidence bundle (evidence.schema.json)
export interface HistogramBucket {
  le: number | string  // string for "+Inf"
  count: number
}

export interface RateSample {
  timestamp: string
  value: number
}

export interface Evidence {
  schema_version: number
  service: string
  namespace: string
  lookback_window: string
  collected_at: string
  coverage_ratio: number
  series: {
    latency_histogram: {
      metric_name: string
      buckets: HistogramBucket[]
      total_count: number
      sum: number
    }
    request_total: {
      metric_name: string
      total: number
      rate_samples?: RateSample[]
    }
    error_total: {
      metric_name: string
      total: number
    }
    saturation?: {
      cpu?: { metric_name: string; samples: number[] }
      memory?: { metric_name: string; samples: number[] }
      available: boolean
    }
  }
  provenance: {
    prometheus_endpoint: string
    query_timestamps: { start: string; end: string }
    queries: Record<string, string>
  }
}

// Baseline artifact (baseline.schema.json)
export interface Baseline {
  schema_version: number
  service: string
  namespace: string
  lookback_window: string
  generated_at: string
  context_type?: 'service' | 'infra'
  maturity_tier?: 'new' | 'growing' | 'mature'
  indicators: {
    latency: {
      p50_ms: number; p90_ms: number; p95_ms: number; p99_ms: number
      stddev_ms: number; sample_count: number; source_query: string
    }
    error_rate: {
      ratio: number; stddev: number
      error_count: number; total_count: number; source_query: string
    }
    availability: {
      ratio: number; definition: string
    }
    throughput: {
      mean_rps: number; p95_rps: number; stddev_rps: number; sample_count: number
    }
    saturation?: {
      cpu_mean_ratio: number; cpu_p95_ratio: number
      memory_mean_ratio: number; memory_p95_ratio: number
      available: boolean
    }
  }
  provenance: {
    prometheus_endpoint: string
    query_timestamps: { start: string; end: string }
    coverage_ratio: number
  }
}

// SLO Proposal (proposal.schema.json v2)
export interface BurnRateWindow {
  long_window: string; short_window: string
  burn_rate: number; severity: string
}

export interface Headroom {
  observed_value: number
  margin: number
  margin_rationale: string
}

export interface SLO {
  sli_name: string
  sli_type: 'latency' | 'availability' | 'throughput' | 'saturation' | 'error_rate'
  sli_definition: string
  slo_target: number
  sla_target: number
  target_op: 'lte' | 'gte'
  target_unit: string
  error_budget_percent: number
  burn_rate_policy: { windows: BurnRateWindow[] }
  headroom?: Headroom
  rationale: string
  requires_review: boolean
  review_reason?: string
}

export interface Proposal {
  schema_version: number
  service: string
  baseline_schema_version: number
  maturity_tier?: string
  slos: SLO[]
}

// Drift signal (drift-signal.schema.json)
export interface DriftIndicator {
  name: string
  live_value: number
  baseline_value: number
  abs_deviation: number
  rel_deviation: number
  direction: 'increasing' | 'decreasing' | 'stable'
  band_upper: number
  band_lower: number
  band_breach: boolean
  first_pass_class: string
  status?: 'measured' | 'skipped'
  skip_reason?: string
}

export interface DominantSignal {
  indicator: string
  class: string
  breach_magnitude: number
}

export interface DriftSignal {
  schema_version: number
  service: string
  evaluation_window: string
  evaluated_at: string
  baseline_schema_version: number
  indicators: DriftIndicator[]
  dominant_signal: DominantSignal
  all_breached_indicators: string[]
  provenance: {
    prometheus_endpoint: string
    query_timestamps: { start: string; end: string }
    coverage_ratio: number
  }
}

// Drift report (drift-report.schema.json)
export interface RemediationPlan {
  priority: 'immediate' | 'short_term' | 'long_term'
  evidence_basis: string
  expected_impact: string
  verification_method: string
}

export interface Recommendation {
  action: string
  confidence: 'high' | 'medium' | 'low'
  rationale: string
  remediation_plan?: RemediationPlan
}

export interface DriftReport {
  schema_version: number
  service: string
  classification: string
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info'
  likely_cause: string
  recommendations: Recommendation[]
}

// Render output
export interface RenderOutput {
  openslo_yaml: string
  prom_rules: string
}

// Fixtures listing
export interface FixturesListing {
  services: string[]
  drift_scenarios: string[]
}

// --- API methods ---

export const api = {
  health: () =>
    request<{ status: string; version: string }>('GET', '/health'),

  collectEvidence: (service: string, namespace: string) =>
    request<Evidence>('POST', '/api/v1/evidence', { service, namespace }),

  computeBaseline: (evidence: Evidence) =>
    request<Baseline>('POST', '/api/v1/baseline', { evidence }),

  proposeSLOs: (baseline: Baseline, maturity = 'growing', contextType = 'service') =>
    request<Proposal>('POST', '/api/v1/propose', { baseline, maturity, context_type: contextType }),

  computeDrift: (baseline: Baseline, liveEvidence: Evidence) =>
    request<DriftSignal>('POST', '/api/v1/drift/signal', { baseline, live_evidence: liveEvidence }),

  classifyDrift: (driftSignal: DriftSignal) =>
    request<DriftReport>('POST', '/api/v1/drift/classify', { drift_signal: driftSignal }),

  renderArtifacts: (proposal: Proposal, service = 'checkout-api') =>
    request<RenderOutput>('POST', '/api/v1/render', { proposal, service }),

  listFixtures: () =>
    request<FixturesListing>('GET', '/api/v1/fixtures'),

  getDriftFixture: (scenario: string) =>
    request<DriftSignal>('GET', `/api/v1/fixtures/drift/${scenario}`),

  getBaselineFixture: (service: string) =>
    request<Baseline>('GET', `/api/v1/fixtures/baseline/${service}`),
}
