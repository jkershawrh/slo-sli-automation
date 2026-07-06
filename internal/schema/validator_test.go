package schema

import (
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
		SchemaVersion:  2, // schema requires const: 1
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
