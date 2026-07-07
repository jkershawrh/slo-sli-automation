// Package prom provides a Prometheus/Thanos HTTP API client for collecting
// telemetry evidence used in SLO baseline computation.
package prom

// QueryResult represents the top-level response from the Prometheus HTTP API.
type QueryResult struct {
	Status string    `json:"status"`
	Data   QueryData `json:"data"`
}

// QueryData holds the result type and the series data returned by a query.
type QueryData struct {
	ResultType string   `json:"resultType"`
	Result     []Series `json:"result"`
}

// Series represents a single time series returned by a Prometheus query.
type Series struct {
	Metric map[string]string `json:"metric"`
	Values []SamplePair      `json:"values,omitempty"` // range query (matrix)
	Value  []interface{}     `json:"value,omitempty"`  // instant query (vector)
}

// SamplePair is a single timestamp/value pair in a time series.
type SamplePair struct {
	Timestamp float64
	Value     float64
}

// EvidenceBundle is the Go representation of the evidence JSON artifact.
type EvidenceBundle struct {
	SchemaVersion  int                `json:"schema_version"`
	Service        string             `json:"service"`
	Namespace      string             `json:"namespace"`
	LookbackWindow string             `json:"lookback_window"`
	CollectedAt    string             `json:"collected_at"`
	CoverageRatio  float64            `json:"coverage_ratio"`
	Series         EvidenceSeries     `json:"series"`
	Provenance     EvidenceProvenance `json:"provenance"`
}

// EvidenceSeries holds the collected metric data for each signal type.
type EvidenceSeries struct {
	LatencyHistogram HistogramData   `json:"latency_histogram"`
	RequestTotal     CounterData     `json:"request_total"`
	ErrorTotal       CounterData     `json:"error_total"`
	Saturation       *SaturationData `json:"saturation,omitempty"`
	Traces           *TraceData      `json:"traces,omitempty"`
	Logs             *LogData        `json:"logs,omitempty"`
}

// HistogramData holds the bucket distribution for a histogram metric.
type HistogramData struct {
	MetricName string            `json:"metric_name"`
	Buckets    []HistogramBucket `json:"buckets"`
	TotalCount float64           `json:"total_count"`
	Sum        float64           `json:"sum"`
}

// HistogramBucket is a single le/count pair in a cumulative histogram.
type HistogramBucket struct {
	Le    float64 `json:"le"`
	Count float64 `json:"count"`
}

// CounterData holds the value of a counter metric and optional rate samples.
type CounterData struct {
	MetricName  string       `json:"metric_name"`
	Total       float64      `json:"total"`
	RateSamples []RateSample `json:"rate_samples,omitempty"`
}

// RateSample is a timestamped rate value.
type RateSample struct {
	Timestamp string  `json:"timestamp"`
	Value     float64 `json:"value"`
}

// SaturationData holds optional resource utilization metrics.
type SaturationData struct {
	CPU       *ResourceSamples `json:"cpu,omitempty"`
	Memory    *ResourceSamples `json:"memory,omitempty"`
	Available bool             `json:"available"`
}

// ResourceSamples holds sampled values for a single resource metric.
type ResourceSamples struct {
	MetricName string    `json:"metric_name"`
	Samples    []float64 `json:"samples"`
}

// EvidenceProvenance records how the evidence was collected for reproducibility.
type EvidenceProvenance struct {
	PrometheusEndpoint string            `json:"prometheus_endpoint"`
	QueryTimestamps    TimeRange         `json:"query_timestamps"`
	Queries            map[string]string `json:"queries"`
}

// TimeRange is a start/end pair of RFC3339 timestamps.
type TimeRange struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

// TraceData holds distributed tracing evidence for a service.
type TraceData struct {
	Available        bool             `json:"available"`
	Source           string           `json:"source"`
	TotalSpans       int              `json:"total_spans"`
	ServiceSpans     int              `json:"service_spans"`
	SpanLatencyP99Ms float64          `json:"span_latency_p99_ms"`
	SpanLatencyP50Ms float64          `json:"span_latency_p50_ms"`
	TopDependencies  []DependencySpan `json:"top_dependencies,omitempty"`
	SlowSpanPattern  string           `json:"slow_span_pattern,omitempty"`
}

// DependencySpan records latency and error data for a downstream dependency.
type DependencySpan struct {
	Service   string  `json:"service"`
	P99Ms     float64 `json:"p99_ms"`
	CallCount int     `json:"call_count"`
	ErrorRate float64 `json:"error_rate"`
}

// LogData holds log-based evidence for a service.
type LogData struct {
	Available           bool               `json:"available"`
	Source              string             `json:"source"`
	TotalEntries        int                `json:"total_entries"`
	ErrorEntries        int                `json:"error_entries"`
	ErrorBreakdown      []ErrorCategory    `json:"error_breakdown,omitempty"`
	ErrorRateByCategory map[string]float64 `json:"error_rate_by_category,omitempty"`
}

// ErrorCategory records the count and ratio for a single error category.
type ErrorCategory struct {
	Category string  `json:"category"`
	Count    int     `json:"count"`
	Ratio    float64 `json:"ratio"`
}
