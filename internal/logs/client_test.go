package logs

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ---------- canned Loki API responses ----------

const lokiQueryResponse = `{
  "status": "success",
  "data": {
    "resultType": "streams",
    "result": [
      {
        "stream": {"service": "api-gateway", "namespace": "production", "level": "error", "error_type": "timeout"},
        "values": [
          ["1609459200000000000", "connection timeout to postgres"],
          ["1609459260000000000", "connection timeout to postgres"],
          ["1609459320000000000", "connection timeout to redis"]
        ]
      },
      {
        "stream": {"service": "api-gateway", "namespace": "production", "level": "error", "error_type": "null_pointer"},
        "values": [
          ["1609459200000000000", "nil pointer dereference in handler"]
        ]
      }
    ]
  }
}`

const lokiEmptyResponse = `{
  "status": "success",
  "data": {
    "resultType": "streams",
    "result": []
  }
}`

// ---------- Test: CollectLogEvidence parses results ----------

func TestCollectLogEvidence_ParsesResult(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/loki/api/v1/query_range" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(lokiQueryResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	ld, err := c.CollectLogEvidence(context.Background(), "api-gateway", "production", 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if !ld.Available {
		t.Error("expected Available=true")
	}
	if ld.Source != "loki" {
		t.Errorf("expected Source=loki, got %s", ld.Source)
	}
	// 3 + 1 = 4 total entries
	if ld.TotalEntries != 4 {
		t.Errorf("expected TotalEntries=4, got %d", ld.TotalEntries)
	}
	if ld.ErrorEntries != 4 {
		t.Errorf("expected ErrorEntries=4, got %d", ld.ErrorEntries)
	}
	if len(ld.ErrorBreakdown) == 0 {
		t.Fatal("expected error_breakdown to be non-empty")
	}
}

// ---------- Test: Bearer token is sent when configured ----------

func TestCollectLogEvidence_BearerToken(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(lokiEmptyResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{
		BaseURL: srv.URL,
		Token:   "my-loki-token",
		Timeout: 5 * time.Second,
	})

	_, err := c.CollectLogEvidence(context.Background(), "svc", "ns", 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	expected := "Bearer my-loki-token"
	if gotAuth != expected {
		t.Errorf("expected Authorization header %q, got %q", expected, gotAuth)
	}
}

// ---------- Test: HTTP error returns clear message ----------

func TestCollectLogEvidence_HttpError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal server error", http.StatusInternalServerError)
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	_, err := c.CollectLogEvidence(context.Background(), "svc", "ns", 1*time.Hour)
	if err == nil {
		t.Fatal("expected error for 500 response")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Errorf("error should mention status code 500: %v", err)
	}
}

// ---------- Test: Categorizes by error_type label ----------

func TestCollectLogEvidence_CategorizesByErrorType(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(lokiQueryResponse))
	}))
	defer srv.Close()

	c := NewClient(ClientConfig{BaseURL: srv.URL, Timeout: 5 * time.Second})

	ld, err := c.CollectLogEvidence(context.Background(), "api-gateway", "production", 1*time.Hour)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Should have 2 categories: timeout (3 entries) and null_pointer (1 entry)
	if len(ld.ErrorBreakdown) != 2 {
		t.Fatalf("expected 2 error categories, got %d", len(ld.ErrorBreakdown))
	}

	// First category (sorted by count desc) should be timeout
	if ld.ErrorBreakdown[0].Category != "timeout" {
		t.Errorf("expected first category to be timeout, got %s", ld.ErrorBreakdown[0].Category)
	}
	if ld.ErrorBreakdown[0].Count != 3 {
		t.Errorf("expected timeout count=3, got %d", ld.ErrorBreakdown[0].Count)
	}
	if ld.ErrorBreakdown[0].Ratio != 0.75 {
		t.Errorf("expected timeout ratio=0.75, got %f", ld.ErrorBreakdown[0].Ratio)
	}

	// Second category should be null_pointer
	if ld.ErrorBreakdown[1].Category != "null_pointer" {
		t.Errorf("expected second category to be null_pointer, got %s", ld.ErrorBreakdown[1].Category)
	}
	if ld.ErrorBreakdown[1].Count != 1 {
		t.Errorf("expected null_pointer count=1, got %d", ld.ErrorBreakdown[1].Count)
	}

	// ErrorRateByCategory should match
	if ld.ErrorRateByCategory["timeout"] != 0.75 {
		t.Errorf("expected ErrorRateByCategory[timeout]=0.75, got %f", ld.ErrorRateByCategory["timeout"])
	}
	if ld.ErrorRateByCategory["null_pointer"] != 0.25 {
		t.Errorf("expected ErrorRateByCategory[null_pointer]=0.25, got %f", ld.ErrorRateByCategory["null_pointer"])
	}
}
