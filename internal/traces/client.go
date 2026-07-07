// Package traces provides a Tempo/Jaeger HTTP API client for collecting
// distributed tracing evidence used in SLO baseline computation.
package traces

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/sloscope/sloscope/internal/prom"
)

// Client talks to a Tempo or Jaeger HTTP API endpoint.
type Client struct {
	baseURL    string
	token      string
	httpClient *http.Client
}

// ClientConfig holds configuration for creating a new Client.
type ClientConfig struct {
	BaseURL string
	Token   string
	Timeout time.Duration
}

// NewClient creates a Client from the given configuration.
func NewClient(cfg ClientConfig) *Client {
	timeout := cfg.Timeout
	if timeout == 0 {
		timeout = 30 * time.Second
	}
	return &Client{
		baseURL:    strings.TrimRight(cfg.BaseURL, "/"),
		token:      cfg.Token,
		httpClient: &http.Client{Timeout: timeout},
	}
}

// CollectTraceEvidence queries Tempo/Jaeger for trace data for a service.
// Returns a TraceData struct ready to merge into the evidence bundle.
func (c *Client) CollectTraceEvidence(ctx context.Context, service string, window time.Duration) (*prom.TraceData, error) {
	url := fmt.Sprintf("%s/api/search?serviceName=%s&limit=1000", c.baseURL, service)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("building trace request: %w", err)
	}
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("querying traces: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("trace query returned %d", resp.StatusCode)
	}

	var result TempoSearchResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decoding trace response: %w", err)
	}

	return aggregateTraces(result, service), nil
}

// TempoSearchResult mirrors the Tempo search API response.
type TempoSearchResult struct {
	Traces []TempoTrace `json:"traces"`
}

// TempoTrace represents a single trace returned by the Tempo search API.
type TempoTrace struct {
	TraceID         string    `json:"traceID"`
	RootServiceName string    `json:"rootServiceName"`
	DurationMs      float64   `json:"durationMs"`
	SpanSets        []SpanSet `json:"spanSets,omitempty"`
}

// SpanSet is a group of spans within a trace.
type SpanSet struct {
	Spans []Span `json:"spans"`
}

// Span represents a single span within a trace.
type Span struct {
	SpanID        string `json:"spanID"`
	Name          string `json:"name"`
	ServiceName   string `json:"serviceName"`
	DurationNanos int64  `json:"durationNanos"`
}

func aggregateTraces(result TempoSearchResult, service string) *prom.TraceData {
	depLatencies := make(map[string][]float64)
	var serviceLatencies []float64
	totalSpans := 0
	serviceSpans := 0

	for _, trace := range result.Traces {
		for _, ss := range trace.SpanSets {
			for _, span := range ss.Spans {
				totalSpans++
				latMs := float64(span.DurationNanos) / 1e6
				if span.ServiceName == service {
					serviceSpans++
					serviceLatencies = append(serviceLatencies, latMs)
				} else {
					depLatencies[span.ServiceName] = append(depLatencies[span.ServiceName], latMs)
				}
			}
		}
	}

	// If no span-level data, use trace-level durations.
	if len(serviceLatencies) == 0 {
		for _, trace := range result.Traces {
			totalSpans++
			serviceSpans++
			serviceLatencies = append(serviceLatencies, trace.DurationMs)
		}
	}

	td := &prom.TraceData{
		Available:    true,
		Source:       "tempo",
		TotalSpans:   totalSpans,
		ServiceSpans: serviceSpans,
	}

	if len(serviceLatencies) > 0 {
		td.SpanLatencyP99Ms = percentile(serviceLatencies, 0.99)
		td.SpanLatencyP50Ms = percentile(serviceLatencies, 0.50)
	}

	// Build top dependencies sorted by p99 latency.
	for dep, lats := range depLatencies {
		p99 := percentile(lats, 0.99)
		td.TopDependencies = append(td.TopDependencies, prom.DependencySpan{
			Service:   dep,
			P99Ms:     p99,
			CallCount: len(lats),
			ErrorRate: 0, // Would need error status from spans.
		})
	}

	// Sort by p99 descending, keep top 5.
	sortDependencies(td.TopDependencies)
	if len(td.TopDependencies) > 5 {
		td.TopDependencies = td.TopDependencies[:5]
	}

	// Set slow span pattern.
	if len(td.TopDependencies) > 0 && td.SpanLatencyP99Ms > 0 {
		top := td.TopDependencies[0]
		contribution := top.P99Ms / td.SpanLatencyP99Ms * 100
		td.SlowSpanPattern = fmt.Sprintf("%s accounts for %.0f%% of p99 tail latency", top.Service, contribution)
	}

	return td
}

func percentile(values []float64, q float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sorted := make([]float64, len(values))
	copy(sorted, values)
	sort.Float64s(sorted)
	idx := int(q * float64(len(sorted)-1))
	return sorted[idx]
}

func sortDependencies(deps []prom.DependencySpan) {
	sort.Slice(deps, func(i, j int) bool {
		return deps[i].P99Ms > deps[j].P99Ms
	})
}
