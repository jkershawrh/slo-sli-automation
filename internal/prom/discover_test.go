package prom

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ---------- canned Prometheus API responses for discovery ----------

// standardVectorResponse returns results for standard metric names.
const standardVectorResponse = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "http_request_duration_seconds_bucket", "service": "api", "namespace": "production"},
        "value": [1609459200, "42"]
      }
    ]
  }
}`

const standardRequestTotalVector = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "http_requests_total", "service": "api", "namespace": "production"},
        "value": [1609459200, "1000"]
      }
    ]
  }
}`

const standardErrorTotalVector = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "http_requests_total", "service": "api", "namespace": "production", "code": "503"},
        "value": [1609459200, "5"]
      }
    ]
  }
}`

const emptyVectorResponse = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": []
  }
}`

const discoveredLatencyVector = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "custom_request_latency_bucket", "namespace": "production"},
        "value": [1609459200, "99"]
      }
    ]
  }
}`

const discoveredRequestVector = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "gateway_http_requests_total", "namespace": "production"},
        "value": [1609459200, "500"]
      }
    ]
  }
}`

const discoveredErrorVector = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "gateway_error_total", "namespace": "production"},
        "value": [1609459200, "3"]
      }
    ]
  }
}`

// ---------- Test: standard metrics found ----------

func TestDiscoverMetrics_StandardFound(t *testing.T) {
	callNum := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("query")
		w.Header().Set("Content-Type", "application/json")

		switch {
		case strings.Contains(query, "duration_seconds_bucket"):
			w.Write([]byte(standardVectorResponse))
		case strings.Contains(query, `code=~"5.."`):
			w.Write([]byte(standardErrorTotalVector))
		case strings.Contains(query, "http_requests_total"):
			w.Write([]byte(standardRequestTotalVector))
		default:
			w.Write([]byte(emptyVectorResponse))
		}
		callNum++
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	dm, err := c.DiscoverMetrics(context.Background(), "api", "production")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if dm.Source != "standard" {
		t.Errorf("expected source 'standard', got %q", dm.Source)
	}
	if dm.LatencyHistogram != "http_request_duration_seconds" {
		t.Errorf("expected LatencyHistogram 'http_request_duration_seconds', got %q", dm.LatencyHistogram)
	}
	if dm.RequestTotal != "http_requests_total" {
		t.Errorf("expected RequestTotal 'http_requests_total', got %q", dm.RequestTotal)
	}
	if dm.ErrorTotal != "http_requests_total" {
		t.Errorf("expected ErrorTotal 'http_requests_total', got %q", dm.ErrorTotal)
	}
}

// ---------- Test: non-standard names discovered via pattern ----------

func TestDiscoverMetrics_DiscoveredViaPattern(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("query")
		w.Header().Set("Content-Type", "application/json")

		switch {
		// Standard queries all return empty (not available)
		case strings.Contains(query, "http_request_duration_seconds_bucket"):
			w.Write([]byte(emptyVectorResponse))
		case strings.Contains(query, "http_requests_total"):
			w.Write([]byte(emptyVectorResponse))

		// Discovery queries return non-standard metric names
		case strings.Contains(query, "duration.*bucket|.*latency.*bucket"):
			w.Write([]byte(discoveredLatencyVector))
		case strings.Contains(query, "request.*total|.*http.*total"):
			w.Write([]byte(discoveredRequestVector))
		case strings.Contains(query, "error.*total|.*fail.*total"):
			w.Write([]byte(discoveredErrorVector))
		default:
			w.Write([]byte(emptyVectorResponse))
		}
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	dm, err := c.DiscoverMetrics(context.Background(), "gateway", "production")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if dm.Source != "discovered" {
		t.Errorf("expected source 'discovered', got %q", dm.Source)
	}
	if dm.LatencyHistogram != "custom_request_latency" {
		t.Errorf("expected LatencyHistogram 'custom_request_latency', got %q", dm.LatencyHistogram)
	}
	if dm.RequestTotal != "gateway_http_requests_total" {
		t.Errorf("expected RequestTotal 'gateway_http_requests_total', got %q", dm.RequestTotal)
	}
	if dm.ErrorTotal != "gateway_error_total" {
		t.Errorf("expected ErrorTotal 'gateway_error_total', got %q", dm.ErrorTotal)
	}
}

// ---------- Test: no app metrics, container-only ----------

func TestDiscoverMetrics_ContainerOnly(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// All queries return empty results
		w.Write([]byte(emptyVectorResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	dm, err := c.DiscoverMetrics(context.Background(), "mystery-svc", "staging")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if dm.Source != "container-only" {
		t.Errorf("expected source 'container-only', got %q", dm.Source)
	}
	if dm.LatencyHistogram != "" {
		t.Errorf("expected empty LatencyHistogram, got %q", dm.LatencyHistogram)
	}
	if dm.RequestTotal != "" {
		t.Errorf("expected empty RequestTotal, got %q", dm.RequestTotal)
	}
	if dm.ErrorTotal != "" {
		t.Errorf("expected empty ErrorTotal, got %q", dm.ErrorTotal)
	}
	if dm.CPUMetric != "container_cpu_usage_seconds_total" {
		t.Errorf("expected CPUMetric 'container_cpu_usage_seconds_total', got %q", dm.CPUMetric)
	}
	if dm.MemoryMetric != "container_memory_working_set_bytes" {
		t.Errorf("expected MemoryMetric 'container_memory_working_set_bytes', got %q", dm.MemoryMetric)
	}
}

// ---------- Test: __name__ extraction and _bucket suffix stripping ----------

func TestDiscoverMetrics_ExtractsMetricName(t *testing.T) {
	// Simulate a scenario where only the latency discovery pattern returns a result
	// with a _bucket suffix that should be stripped.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("query")
		w.Header().Set("Content-Type", "application/json")

		switch {
		// Standard queries return empty
		case strings.Contains(query, "http_request_duration_seconds_bucket"):
			w.Write([]byte(emptyVectorResponse))
		case strings.Contains(query, "http_requests_total"):
			w.Write([]byte(emptyVectorResponse))

		// Discovery: latency returns a bucket metric name
		case strings.Contains(query, "duration.*bucket|.*latency.*bucket"):
			w.Write([]byte(`{
				"status": "success",
				"data": {
					"resultType": "vector",
					"result": [{
						"metric": {"__name__": "envoy_http_downstream_rq_time_bucket", "namespace": "production"},
						"value": [1609459200, "77"]
					}]
				}
			}`))
		// Discovery: request returns a total metric (no suffix to strip)
		case strings.Contains(query, "request.*total|.*http.*total"):
			w.Write([]byte(`{
				"status": "success",
				"data": {
					"resultType": "vector",
					"result": [{
						"metric": {"__name__": "envoy_http_downstream_rq_total", "namespace": "production"},
						"value": [1609459200, "200"]
					}]
				}
			}`))
		default:
			w.Write([]byte(emptyVectorResponse))
		}
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	dm, err := c.DiscoverMetrics(context.Background(), "envoy", "production")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if dm.Source != "discovered" {
		t.Errorf("expected source 'discovered', got %q", dm.Source)
	}

	// _bucket suffix should be stripped for the histogram base name
	if dm.LatencyHistogram != "envoy_http_downstream_rq_time" {
		t.Errorf("expected LatencyHistogram 'envoy_http_downstream_rq_time' (bucket suffix stripped), got %q", dm.LatencyHistogram)
	}

	// _total suffix should NOT be stripped (it's part of the counter name)
	if dm.RequestTotal != "envoy_http_downstream_rq_total" {
		t.Errorf("expected RequestTotal 'envoy_http_downstream_rq_total', got %q", dm.RequestTotal)
	}
}
