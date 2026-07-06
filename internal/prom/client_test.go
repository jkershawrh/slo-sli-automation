package prom

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ---------- canned Prometheus API responses ----------

const matrixResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"__name__": "http_requests_total", "service": "api"},
        "values": [[1609459200, "100"], [1609459260, "150"]]
      }
    ]
  }
}`

const vectorResponse = `{
  "status": "success",
  "data": {
    "resultType": "vector",
    "result": [
      {
        "metric": {"__name__": "up", "instance": "localhost:9090"},
        "value": [1609459200, "1"]
      }
    ]
  }
}`

const histogramBucketResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"__name__": "http_request_duration_seconds_bucket", "le": "0.1"},
        "values": [[1609459200, "80"], [1609459260, "90"]]
      },
      {
        "metric": {"__name__": "http_request_duration_seconds_bucket", "le": "0.5"},
        "values": [[1609459200, "95"], [1609459260, "98"]]
      },
      {
        "metric": {"__name__": "http_request_duration_seconds_bucket", "le": "+Inf"},
        "values": [[1609459200, "100"], [1609459260, "100"]]
      }
    ]
  }
}`

const requestTotalResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"__name__": "http_requests_total", "service": "api"},
        "values": [[1609459200, "1000"], [1609459260, "1050"]]
      }
    ]
  }
}`

const errorTotalResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"__name__": "http_requests_total", "service": "api", "code": "500"},
        "values": [[1609459200, "10"], [1609459260, "12"]]
      }
    ]
  }
}`

const emptyResultResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": []
  }
}`

const sumResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"__name__": "http_request_duration_seconds_sum"},
        "values": [[1609459200, "45.5"], [1609459260, "50.2"]]
      }
    ]
  }
}`

const countResponse = `{
  "status": "success",
  "data": {
    "resultType": "matrix",
    "result": [
      {
        "metric": {"__name__": "http_request_duration_seconds_count"},
        "values": [[1609459200, "100"], [1609459260, "110"]]
      }
    ]
  }
}`

// ---------- Test: QueryRange returns parsed results ----------

func TestQueryRange_ParsesMatrix(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/query_range" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(matrixResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	start := time.Unix(1609459200, 0)
	end := time.Unix(1609459260, 0)
	res, err := c.QueryRange(context.Background(), "http_requests_total", start, end, 60*time.Second)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if res.Status != "success" {
		t.Errorf("expected status success, got %s", res.Status)
	}
	if res.Data.ResultType != "matrix" {
		t.Errorf("expected resultType matrix, got %s", res.Data.ResultType)
	}
	if len(res.Data.Result) != 1 {
		t.Fatalf("expected 1 series, got %d", len(res.Data.Result))
	}

	series := res.Data.Result[0]
	if series.Metric["__name__"] != "http_requests_total" {
		t.Errorf("unexpected metric name: %v", series.Metric)
	}
	if len(series.Values) != 2 {
		t.Fatalf("expected 2 values, got %d", len(series.Values))
	}
	if series.Values[0].Value != 100 {
		t.Errorf("expected first value 100, got %f", series.Values[0].Value)
	}
	if series.Values[1].Value != 150 {
		t.Errorf("expected second value 150, got %f", series.Values[1].Value)
	}
}

// ---------- Test: InstantQuery returns parsed results ----------

func TestInstantQuery_ParsesVector(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/query" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(vectorResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	res, err := c.InstantQuery(context.Background(), "up", time.Unix(1609459200, 0))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if res.Status != "success" {
		t.Errorf("expected status success, got %s", res.Status)
	}
	if res.Data.ResultType != "vector" {
		t.Errorf("expected resultType vector, got %s", res.Data.ResultType)
	}
	if len(res.Data.Result) != 1 {
		t.Fatalf("expected 1 result, got %d", len(res.Data.Result))
	}

	r := res.Data.Result[0]
	if r.Metric["__name__"] != "up" {
		t.Errorf("unexpected metric: %v", r.Metric)
	}
}

// ---------- Test: Bearer token is sent when configured ----------

func TestBearerToken_Sent(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(vectorResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{
		BaseURL: srv.URL,
		Token:   "my-secret-token",
		Timeout: 5 * time.Second,
	})

	_, err := c.InstantQuery(context.Background(), "up", time.Now())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	expected := "Bearer my-secret-token"
	if gotAuth != expected {
		t.Errorf("expected Authorization header %q, got %q", expected, gotAuth)
	}
}

// ---------- Test: No auth header when token is empty ----------

func TestNoAuthHeader_WhenTokenEmpty(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(vectorResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	_, err := c.InstantQuery(context.Background(), "up", time.Now())
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if gotAuth != "" {
		t.Errorf("expected no Authorization header, got %q", gotAuth)
	}
}

// ---------- Test: HTTP errors return clear error messages ----------

func TestHTTPError_ReturnsClearMessage(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	_, err := c.InstantQuery(context.Background(), "up", time.Now())
	if err == nil {
		t.Fatal("expected error for 500 response")
	}

	if !strings.Contains(err.Error(), "500") {
		t.Errorf("error should mention status code 500: %v", err)
	}
}

// ---------- Test: Timeout is enforced ----------

func TestTimeout_Enforced(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Simulate a slow endpoint. The client timeout should fire first.
		time.Sleep(2 * time.Second)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(vectorResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{
		BaseURL: srv.URL,
		Timeout: 100 * time.Millisecond,
	})

	_, err := c.InstantQuery(context.Background(), "up", time.Now())
	if err == nil {
		t.Fatal("expected timeout error")
	}

	errStr := err.Error()
	if !strings.Contains(errStr, "deadline") && !strings.Contains(errStr, "timeout") &&
		!strings.Contains(errStr, "Timeout") && !strings.Contains(errStr, "canceled") {
		t.Errorf("error should indicate a timeout: %v", err)
	}
}

// ---------- Test: CollectEvidence assembles a valid bundle ----------

func TestCollectEvidence_AssemblesBundle(t *testing.T) {
	callCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("query")
		w.Header().Set("Content-Type", "application/json")

		switch {
		case strings.Contains(query, "bucket"):
			w.Write([]byte(histogramBucketResponse))
		case strings.Contains(query, "duration_seconds_sum"):
			w.Write([]byte(sumResponse))
		case strings.Contains(query, "duration_seconds_count"):
			w.Write([]byte(countResponse))
		case strings.Contains(query, `code=~"5.."`):
			w.Write([]byte(errorTotalResponse))
		case strings.Contains(query, "http_requests_total"):
			w.Write([]byte(requestTotalResponse))
		case strings.Contains(query, "cpu") || strings.Contains(query, "memory"):
			// Saturation metrics are not available.
			w.Write([]byte(emptyResultResponse))
		default:
			w.Write([]byte(emptyResultResponse))
		}
		callCount++
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	bundle, err := c.CollectEvidence(context.Background(), "api", "production", 7*24*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Validate top-level fields.
	if bundle.SchemaVersion != 1 {
		t.Errorf("expected schema_version 1, got %d", bundle.SchemaVersion)
	}
	if bundle.Service != "api" {
		t.Errorf("expected service api, got %s", bundle.Service)
	}
	if bundle.Namespace != "production" {
		t.Errorf("expected namespace production, got %s", bundle.Namespace)
	}
	if bundle.LookbackWindow != "7d" {
		t.Errorf("expected lookback_window 7d, got %s", bundle.LookbackWindow)
	}
	if bundle.CollectedAt == "" {
		t.Error("expected collected_at to be set")
	}
	if bundle.CoverageRatio < 0 || bundle.CoverageRatio > 1 {
		t.Errorf("coverage_ratio out of range: %f", bundle.CoverageRatio)
	}

	// Validate series.
	if bundle.Series.LatencyHistogram.MetricName == "" {
		t.Error("expected latency_histogram.metric_name to be set")
	}
	if len(bundle.Series.LatencyHistogram.Buckets) == 0 {
		t.Error("expected latency_histogram.buckets to be non-empty")
	}
	if bundle.Series.RequestTotal.MetricName == "" {
		t.Error("expected request_total.metric_name to be set")
	}
	if bundle.Series.RequestTotal.Total <= 0 {
		t.Error("expected request_total.total > 0")
	}
	if bundle.Series.ErrorTotal.MetricName == "" {
		t.Error("expected error_total.metric_name to be set")
	}

	// Saturation should be present but not available since we returned empty.
	if bundle.Series.Saturation == nil {
		t.Error("expected saturation to be present")
	} else if bundle.Series.Saturation.Available {
		t.Error("expected saturation.available to be false")
	}

	// Validate provenance.
	if bundle.Provenance.PrometheusEndpoint == "" {
		t.Error("expected provenance.prometheus_endpoint to be set")
	}
	if bundle.Provenance.QueryTimestamps.Start == "" || bundle.Provenance.QueryTimestamps.End == "" {
		t.Error("expected provenance.query_timestamps to be set")
	}
	if len(bundle.Provenance.Queries) == 0 {
		t.Error("expected provenance.queries to be non-empty")
	}

	// Verify it's valid JSON that round-trips.
	data, err := json.Marshal(bundle)
	if err != nil {
		t.Fatalf("failed to marshal bundle: %v", err)
	}
	var roundTrip EvidenceBundle
	if err := json.Unmarshal(data, &roundTrip); err != nil {
		t.Fatalf("failed to unmarshal bundle: %v", err)
	}
	if roundTrip.Service != bundle.Service {
		t.Errorf("round-trip service mismatch: %s vs %s", roundTrip.Service, bundle.Service)
	}
}

// ---------- Test: QueryRange sends correct query parameters ----------

func TestQueryRange_SendsCorrectParams(t *testing.T) {
	var gotQuery, gotStart, gotEnd, gotStep string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.Query().Get("query")
		gotStart = r.URL.Query().Get("start")
		gotEnd = r.URL.Query().Get("end")
		gotStep = r.URL.Query().Get("step")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(matrixResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	start := time.Unix(1609459200, 0)
	end := time.Unix(1609459260, 0)
	_, err := c.QueryRange(context.Background(), "my_metric", start, end, 60*time.Second)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if gotQuery != "my_metric" {
		t.Errorf("expected query my_metric, got %s", gotQuery)
	}
	if gotStart == "" {
		t.Error("expected start param to be set")
	}
	if gotEnd == "" {
		t.Error("expected end param to be set")
	}
	if gotStep == "" {
		t.Error("expected step param to be set")
	}
}
