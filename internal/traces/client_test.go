package traces

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ---------- canned Tempo API responses ----------

const tempoSearchResponse = `{
  "traces": [
    {
      "traceID": "abc123",
      "rootServiceName": "api-gateway",
      "durationMs": 150.5,
      "spanSets": [
        {
          "spans": [
            {"spanID": "s1", "name": "GET /users", "serviceName": "api-gateway", "durationNanos": 150000000},
            {"spanID": "s2", "name": "query", "serviceName": "postgres", "durationNanos": 80000000},
            {"spanID": "s3", "name": "cache.get", "serviceName": "redis", "durationNanos": 5000000}
          ]
        }
      ]
    },
    {
      "traceID": "def456",
      "rootServiceName": "api-gateway",
      "durationMs": 200.0,
      "spanSets": [
        {
          "spans": [
            {"spanID": "s4", "name": "GET /orders", "serviceName": "api-gateway", "durationNanos": 200000000},
            {"spanID": "s5", "name": "query", "serviceName": "postgres", "durationNanos": 120000000},
            {"spanID": "s6", "name": "publish", "serviceName": "kafka", "durationNanos": 30000000}
          ]
        }
      ]
    }
  ]
}`

const tempoEmptyResponse = `{
  "traces": []
}`

// ---------- Test: CollectTraceEvidence parses results ----------

func TestCollectTraceEvidence_ParsesResult(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/search" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		svc := r.URL.Query().Get("serviceName")
		if svc != "api-gateway" {
			t.Errorf("expected serviceName=api-gateway, got %s", svc)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(tempoSearchResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	td, err := c.CollectTraceEvidence(context.Background(), "api-gateway", 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !td.Available {
		t.Error("expected Available=true")
	}
	if td.Source != "tempo" {
		t.Errorf("expected Source=tempo, got %s", td.Source)
	}
	// 6 spans total across both traces
	if td.TotalSpans != 6 {
		t.Errorf("expected TotalSpans=6, got %d", td.TotalSpans)
	}
	// 2 spans belong to api-gateway
	if td.ServiceSpans != 2 {
		t.Errorf("expected ServiceSpans=2, got %d", td.ServiceSpans)
	}
	if td.SpanLatencyP99Ms <= 0 {
		t.Errorf("expected SpanLatencyP99Ms > 0, got %f", td.SpanLatencyP99Ms)
	}
	if td.SpanLatencyP50Ms <= 0 {
		t.Errorf("expected SpanLatencyP50Ms > 0, got %f", td.SpanLatencyP50Ms)
	}
	// Should have dependencies: postgres, redis, kafka
	if len(td.TopDependencies) == 0 {
		t.Fatal("expected top_dependencies to be non-empty")
	}
	// Top dependency should be postgres (highest p99)
	if td.TopDependencies[0].Service != "postgres" {
		t.Errorf("expected top dependency to be postgres, got %s", td.TopDependencies[0].Service)
	}
	if td.TopDependencies[0].CallCount != 2 {
		t.Errorf("expected postgres call_count=2, got %d", td.TopDependencies[0].CallCount)
	}
	if td.SlowSpanPattern == "" {
		t.Error("expected slow_span_pattern to be set")
	}
}

// ---------- Test: Bearer token is sent when configured ----------

func TestCollectTraceEvidence_BearerToken(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(tempoEmptyResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{
		BaseURL: srv.URL,
		Token:   "my-tempo-token",
		Timeout: 5 * time.Second,
	})

	_, err := c.CollectTraceEvidence(context.Background(), "svc", 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	expected := "Bearer my-tempo-token"
	if gotAuth != expected {
		t.Errorf("expected Authorization header %q, got %q", expected, gotAuth)
	}
}

// ---------- Test: HTTP error returns clear message ----------

func TestCollectTraceEvidence_HttpError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	_, err := c.CollectTraceEvidence(context.Background(), "svc", 1*time.Hour)
	if err == nil {
		t.Fatal("expected error for 500 response")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Errorf("error should mention status code 500: %v", err)
	}
}

// ---------- Test: Empty result returns Available=true with zero spans ----------

func TestCollectTraceEvidence_EmptyResult(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(tempoEmptyResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	td, err := c.CollectTraceEvidence(context.Background(), "svc", 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !td.Available {
		t.Error("expected Available=true even for empty results")
	}
	if td.TotalSpans != 0 {
		t.Errorf("expected TotalSpans=0, got %d", td.TotalSpans)
	}
	if td.ServiceSpans != 0 {
		t.Errorf("expected ServiceSpans=0, got %d", td.ServiceSpans)
	}
	if td.SpanLatencyP99Ms != 0 {
		t.Errorf("expected SpanLatencyP99Ms=0, got %f", td.SpanLatencyP99Ms)
	}
	if len(td.TopDependencies) != 0 {
		t.Errorf("expected no top_dependencies, got %d", len(td.TopDependencies))
	}
}
