package schema

import (
	"encoding/json"
	"errors"
	"os"
	"testing"

	"github.com/sloscope/sloscope/internal/prom"
)

const schemaDir = "../../analysis/schemas"

func TestValidate_ValidEvidenceBundle(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/evidence.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	bundle := &prom.EvidenceBundle{
		SchemaVersion:  1,
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "http_request_duration_seconds",
				Buckets: []prom.HistogramBucket{
					{Le: 0.1, Count: 80},
					{Le: 0.5, Count: 95},
				},
				TotalCount: 100,
				Sum:        45.5,
			},
			RequestTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      1000,
			},
			ErrorTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      10,
			},
			Saturation: &prom.SaturationData{
				Available: false,
			},
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prometheus:9090",
			QueryTimestamps: prom.TimeRange{
				Start: "2024-12-25T00:00:00Z",
				End:   "2025-01-01T00:00:00Z",
			},
			Queries: map[string]string{
				"latency": `http_request_duration_seconds_bucket{service="api"}`,
			},
		},
	}

	err := v.Validate(bundle, "evidence.schema.json")
	if err != nil {
		t.Fatalf("expected valid bundle, got error: %v", err)
	}
}

func TestValidate_InvalidEvidenceBundle_MissingService(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/evidence.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	bundle := &prom.EvidenceBundle{
		SchemaVersion:  1,
		Service:        "", // empty - violates minLength: 1
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "http_request_duration_seconds",
				Buckets:    []prom.HistogramBucket{{Le: 0.1, Count: 80}},
			},
			RequestTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      1000,
			},
			ErrorTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      10,
			},
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prometheus:9090",
			QueryTimestamps: prom.TimeRange{
				Start: "2024-12-25T00:00:00Z",
				End:   "2025-01-01T00:00:00Z",
			},
			Queries: map[string]string{"q": "up"},
		},
	}

	err := v.Validate(bundle, "evidence.schema.json")
	if err == nil {
		t.Fatal("expected validation error for empty service")
	}

	var ve *ValidationError
	if !errors.As(err, &ve) {
		t.Errorf("expected ValidationError, got %T", err)
	}
}

func TestValidate_InvalidEvidenceBundle_WrongSchemaVersion(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/evidence.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	bundle := &prom.EvidenceBundle{
		SchemaVersion:  99, // schema allows 1-2, so 99 should fail
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "http_request_duration_seconds",
				Buckets:    []prom.HistogramBucket{{Le: 0.1, Count: 80}},
			},
			RequestTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      1000,
			},
			ErrorTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      10,
			},
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prometheus:9090",
			QueryTimestamps: prom.TimeRange{
				Start: "2024-12-25T00:00:00Z",
				End:   "2025-01-01T00:00:00Z",
			},
			Queries: map[string]string{"q": "up"},
		},
	}

	err := v.Validate(bundle, "evidence.schema.json")
	if err == nil {
		t.Fatal("expected validation error for wrong schema_version")
	}
}

func TestValidate_InvalidEvidenceBundle_CoverageOutOfRange(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/evidence.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	bundle := &prom.EvidenceBundle{
		SchemaVersion:  1,
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  1.5, // exceeds maximum of 1
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "http_request_duration_seconds",
				Buckets:    []prom.HistogramBucket{{Le: 0.1, Count: 80}},
			},
			RequestTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      1000,
			},
			ErrorTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      10,
			},
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prometheus:9090",
			QueryTimestamps: prom.TimeRange{
				Start: "2024-12-25T00:00:00Z",
				End:   "2025-01-01T00:00:00Z",
			},
			Queries: map[string]string{"q": "up"},
		},
	}

	err := v.Validate(bundle, "evidence.schema.json")
	if err == nil {
		t.Fatal("expected validation error for coverage_ratio > 1")
	}
}

func TestValidate_SchemaNotFound(t *testing.T) {
	v := NewValidatorFromDir(schemaDir)

	err := v.Validate(map[string]string{"foo": "bar"}, "nonexistent.schema.json")
	if err == nil {
		t.Fatal("expected error for missing schema")
	}
}

func TestValidate_ValidBaselineArtifact(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/baseline.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	baseline := map[string]interface{}{
		"schema_version":  1,
		"service":         "api",
		"namespace":       "production",
		"lookback_window": "7d",
		"generated_at":    "2025-01-01T00:00:00Z",
		"indicators": map[string]interface{}{
			"latency": map[string]interface{}{
				"p50_ms":       50.0,
				"p90_ms":       100.0,
				"p95_ms":       150.0,
				"p99_ms":       200.0,
				"stddev_ms":    25.0,
				"sample_count": 1000,
				"source_query": "histogram_quantile(0.5, rate(http_request_duration_seconds_bucket[5m]))",
			},
			"error_rate": map[string]interface{}{
				"ratio":        0.01,
				"stddev":       0.005,
				"error_count":  10,
				"total_count":  1000,
				"source_query": "rate(http_requests_total{code=~\"5..\"}[5m])",
			},
			"availability": map[string]interface{}{
				"ratio":      0.999,
				"definition": "1 - (error_count / total_count)",
			},
			"throughput": map[string]interface{}{
				"mean_rps":     100.0,
				"p95_rps":      200.0,
				"stddev_rps":   25.0,
				"sample_count": 1000,
			},
		},
		"provenance": map[string]interface{}{
			"prometheus_endpoint": "http://prometheus:9090",
			"query_timestamps": map[string]interface{}{
				"start": "2024-12-25T00:00:00Z",
				"end":   "2025-01-01T00:00:00Z",
			},
			"coverage_ratio": 0.95,
		},
	}

	err := v.Validate(baseline, "baseline.schema.json")
	if err != nil {
		t.Fatalf("expected valid baseline, got error: %v", err)
	}
}

// ---------------------------------------------------------------------------
// Multi-signal (v2) evidence tests
// ---------------------------------------------------------------------------

func TestValidate_EvidenceV2WithTracesAndLogs(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/evidence.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	bundle := &prom.EvidenceBundle{
		SchemaVersion:  2,
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "http_request_duration_seconds",
				Buckets: []prom.HistogramBucket{
					{Le: 0.1, Count: 80},
					{Le: 0.5, Count: 95},
				},
				TotalCount: 100,
				Sum:        45.5,
			},
			RequestTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      1000,
			},
			ErrorTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      10,
			},
			Traces: &prom.TraceData{
				Available:        true,
				Source:           "tempo",
				TotalSpans:       50000,
				ServiceSpans:     12000,
				SpanLatencyP99Ms: 450.0,
				SpanLatencyP50Ms: 25.0,
				TopDependencies: []prom.DependencySpan{
					{Service: "inventory-api", P99Ms: 120.0, CallCount: 8000, ErrorRate: 0.002},
					{Service: "payment-gateway", P99Ms: 300.0, CallCount: 4000, ErrorRate: 0.005},
				},
				SlowSpanPattern: "payment-gateway -> stripe-api",
			},
			Logs: &prom.LogData{
				Available:    true,
				Source:       "loki",
				TotalEntries: 200000,
				ErrorEntries: 460,
				ErrorBreakdown: []prom.ErrorCategory{
					{Category: "timeout", Count: 200, Ratio: 0.435},
					{Category: "connection_refused", Count: 150, Ratio: 0.326},
				},
				ErrorRateByCategory: map[string]float64{
					"timeout":            0.001,
					"connection_refused": 0.00075,
				},
			},
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prometheus:9090",
			QueryTimestamps: prom.TimeRange{
				Start: "2024-12-25T00:00:00Z",
				End:   "2025-01-01T00:00:00Z",
			},
			Queries: map[string]string{
				"latency": `http_request_duration_seconds_bucket{service="api"}`,
			},
		},
	}

	err := v.Validate(bundle, "evidence.schema.json")
	if err != nil {
		t.Fatalf("expected valid v2 evidence with traces+logs, got error: %v", err)
	}
}

func TestValidate_EvidenceV2WithoutTracesOrLogs(t *testing.T) {
	if _, err := os.Stat(schemaDir + "/evidence.schema.json"); err != nil {
		t.Skip("schema files not found at", schemaDir)
	}

	v := NewValidatorFromDir(schemaDir)

	bundle := &prom.EvidenceBundle{
		SchemaVersion:  2,
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "http_request_duration_seconds",
				Buckets:    []prom.HistogramBucket{{Le: 0.1, Count: 80}},
				TotalCount: 100,
				Sum:        45.5,
			},
			RequestTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      1000,
			},
			ErrorTotal: prom.CounterData{
				MetricName: "http_requests_total",
				Total:      10,
			},
			// No Traces or Logs - omitempty fields
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prometheus:9090",
			QueryTimestamps: prom.TimeRange{
				Start: "2024-12-25T00:00:00Z",
				End:   "2025-01-01T00:00:00Z",
			},
			Queries: map[string]string{"q": "up"},
		},
	}

	err := v.Validate(bundle, "evidence.schema.json")
	if err != nil {
		t.Fatalf("expected valid v2 evidence without traces/logs, got error: %v", err)
	}
}

func TestMarshalUnmarshal_EvidenceWithTraceData(t *testing.T) {
	bundle := prom.EvidenceBundle{
		SchemaVersion:  2,
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "m",
				Buckets:    []prom.HistogramBucket{{Le: 1, Count: 10}},
			},
			RequestTotal: prom.CounterData{MetricName: "m", Total: 100},
			ErrorTotal:   prom.CounterData{MetricName: "m", Total: 1},
			Traces: &prom.TraceData{
				Available:        true,
				Source:           "tempo",
				TotalSpans:       5000,
				ServiceSpans:     1200,
				SpanLatencyP99Ms: 450.0,
				SpanLatencyP50Ms: 25.0,
				TopDependencies: []prom.DependencySpan{
					{Service: "db", P99Ms: 120.0, CallCount: 800, ErrorRate: 0.01},
				},
				SlowSpanPattern: "db -> postgres",
			},
			Logs: &prom.LogData{
				Available:    true,
				Source:       "loki",
				TotalEntries: 20000,
				ErrorEntries: 46,
				ErrorBreakdown: []prom.ErrorCategory{
					{Category: "timeout", Count: 20, Ratio: 0.435},
				},
				ErrorRateByCategory: map[string]float64{"timeout": 0.001},
			},
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prom:9090",
			QueryTimestamps:    prom.TimeRange{Start: "2025-01-01T00:00:00Z", End: "2025-01-02T00:00:00Z"},
			Queries:            map[string]string{"q": "up"},
		},
	}

	data, err := json.Marshal(bundle)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	var decoded prom.EvidenceBundle
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	// Verify trace data survived round-trip
	if decoded.Series.Traces == nil {
		t.Fatal("traces should not be nil after round-trip")
	}
	if decoded.Series.Traces.Source != "tempo" {
		t.Errorf("expected traces.source=tempo, got %s", decoded.Series.Traces.Source)
	}
	if decoded.Series.Traces.TotalSpans != 5000 {
		t.Errorf("expected traces.total_spans=5000, got %d", decoded.Series.Traces.TotalSpans)
	}
	if len(decoded.Series.Traces.TopDependencies) != 1 {
		t.Errorf("expected 1 dependency, got %d", len(decoded.Series.Traces.TopDependencies))
	}
	if decoded.Series.Traces.TopDependencies[0].Service != "db" {
		t.Errorf("expected dependency service=db, got %s", decoded.Series.Traces.TopDependencies[0].Service)
	}

	// Verify log data survived round-trip
	if decoded.Series.Logs == nil {
		t.Fatal("logs should not be nil after round-trip")
	}
	if decoded.Series.Logs.Source != "loki" {
		t.Errorf("expected logs.source=loki, got %s", decoded.Series.Logs.Source)
	}
	if decoded.Series.Logs.ErrorEntries != 46 {
		t.Errorf("expected logs.error_entries=46, got %d", decoded.Series.Logs.ErrorEntries)
	}
	if len(decoded.Series.Logs.ErrorBreakdown) != 1 {
		t.Errorf("expected 1 error category, got %d", len(decoded.Series.Logs.ErrorBreakdown))
	}
}

func TestMarshalUnmarshal_EvidenceWithoutTraceData(t *testing.T) {
	bundle := prom.EvidenceBundle{
		SchemaVersion:  1,
		Service:        "api",
		Namespace:      "production",
		LookbackWindow: "7d",
		CollectedAt:    "2025-01-01T00:00:00Z",
		CoverageRatio:  0.95,
		Series: prom.EvidenceSeries{
			LatencyHistogram: prom.HistogramData{
				MetricName: "m",
				Buckets:    []prom.HistogramBucket{{Le: 1, Count: 10}},
			},
			RequestTotal: prom.CounterData{MetricName: "m", Total: 100},
			ErrorTotal:   prom.CounterData{MetricName: "m", Total: 1},
			// No Traces or Logs
		},
		Provenance: prom.EvidenceProvenance{
			PrometheusEndpoint: "http://prom:9090",
			QueryTimestamps:    prom.TimeRange{Start: "2025-01-01T00:00:00Z", End: "2025-01-02T00:00:00Z"},
			Queries:            map[string]string{"q": "up"},
		},
	}

	data, err := json.Marshal(bundle)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}

	// Verify traces and logs keys are omitted from JSON
	var raw map[string]interface{}
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("unmarshal to map failed: %v", err)
	}
	series := raw["series"].(map[string]interface{})
	if _, ok := series["traces"]; ok {
		t.Error("traces key should be omitted when nil")
	}
	if _, ok := series["logs"]; ok {
		t.Error("logs key should be omitted when nil")
	}

	// Verify round-trip
	var decoded prom.EvidenceBundle
	if err := json.Unmarshal(data, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}
	if decoded.Series.Traces != nil {
		t.Error("traces should be nil after round-trip with no trace data")
	}
	if decoded.Series.Logs != nil {
		t.Error("logs should be nil after round-trip with no log data")
	}
}
