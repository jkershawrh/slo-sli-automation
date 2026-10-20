package prom

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/sloscope/sloscope/internal/names"
)

// Client talks to a Prometheus or Thanos HTTP API endpoint.
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
		baseURL: strings.TrimRight(cfg.BaseURL, "/"),
		token:   cfg.Token,
		httpClient: &http.Client{
			Timeout: timeout,
		},
	}
}

// QueryRange executes a Prometheus range query and returns the result matrix.
func (c *Client) QueryRange(ctx context.Context, query string, start, end time.Time, step time.Duration) (*QueryResult, error) {
	params := url.Values{
		"query": {query},
		"start": {formatTime(start)},
		"end":   {formatTime(end)},
		"step":  {strconv.FormatFloat(step.Seconds(), 'f', -1, 64)},
	}
	return c.doQuery(ctx, "/api/v1/query_range", params)
}

// InstantQuery executes a Prometheus instant query and returns the result vector.
func (c *Client) InstantQuery(ctx context.Context, query string, t time.Time) (*QueryResult, error) {
	params := url.Values{
		"query": {query},
		"time":  {formatTime(t)},
	}
	return c.doQuery(ctx, "/api/v1/query", params)
}

// doQuery performs the actual HTTP request and decodes the Prometheus API response.
func (c *Client) doQuery(ctx context.Context, path string, params url.Values) (*QueryResult, error) {
	u := c.baseURL + path + "?" + params.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}

	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("prometheus query: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("reading response body: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("prometheus API returned HTTP %d: %s", resp.StatusCode, truncate(string(body), 200))
	}

	var result QueryResult
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("decoding prometheus response: %w", err)
	}

	if result.Status != "success" || len(result.Warnings) > 0 {
		return nil, fmt.Errorf("prometheus query failed or returned partial-data warnings")
	}
	return &result, nil
}

// CollectEvidence gathers all telemetry for a service over a lookback window
// and returns an evidence bundle ready for baseline computation.
func (c *Client) CollectEvidence(ctx context.Context, service, namespace string, lookback time.Duration) (*EvidenceBundle, error) {
	if err := names.ValidateKubernetesName("service", service); err != nil {
		return nil, err
	}
	if err := names.ValidateKubernetesName("namespace", namespace); err != nil {
		return nil, err
	}

	if lookback < 2*time.Minute || lookback > 30*24*time.Hour {
		return nil, fmt.Errorf("lookback must be between 2m and 30d")
	}
	now := time.Now().UTC().Truncate(time.Second)
	start := now.Add(-lookback)
	step := computeStep(lookback)
	queryStart := start.Add(step)
	queries := buildQueries(service, namespace)
	provQueries := make(map[string]string)

	// increase runs on each original counter before aggregation, so independent
	// instance resets cannot cancel increases from other instances.
	interval := formatDuration(lookback)
	instant := func(name, selector string) (*QueryResult, error) {
		query := fmt.Sprintf("increase(%s[%s])", selector, interval)
		provQueries[name] = query
		res, err := c.InstantQuery(ctx, query, now)
		if err != nil {
			return nil, fmt.Errorf("querying %s: %w", name, err)
		}
		if res.Data.ResultType != "vector" {
			return nil, fmt.Errorf("%s must return an instant vector", name)
		}
		return res, nil
	}
	histRes, err := instant("latency_histogram", queries.histogramBuckets)
	if err != nil {
		return nil, err
	}
	sumRes, err := instant("latency_sum", queries.histogramSum)
	if err != nil {
		return nil, err
	}
	countRes, err := instant("latency_count", queries.histogramCount)
	if err != nil {
		return nil, err
	}
	reqRes, err := instant("request_total", queries.requestTotal)
	if err != nil {
		return nil, err
	}
	errRes, err := instant("error_total", queries.errorTotal)
	if err != nil {
		return nil, err
	}

	histogram, err := assembleIntervalHistogram(histRes, sumRes, countRes)
	if err != nil {
		return nil, err
	}
	requestTotal, errorTotal, err := assembleIntervalCounters(reqRes, errRes)
	if err != nil {
		return nil, err
	}

	// Throughput samples must be rates, never lifetime counter values.
	rateQuery := fmt.Sprintf("sum(rate(%s[%s]))", queries.requestTotal, queryDuration(step))
	provQueries["request_rate"] = rateQuery
	rateRes, err := c.QueryRange(ctx, rateQuery, queryStart, now, step)
	if err != nil {
		return nil, fmt.Errorf("querying request rate: %w", err)
	}
	requestTotal.RateSamples, err = assembleRates(rateRes)
	if err != nil {
		return nil, err
	}

	// Coverage is the minimum fraction of observed time bins for EVERY original
	// series in each required family. Buckets/codes/instances cannot multiply it.
	// This is sample-presence coverage, not an inventory or scrape-success proof.
	coverageRatio := 1.0
	families := []struct {
		name, selector string
		totals         *QueryResult
	}{
		{"latency_histogram", queries.histogramBuckets, histRes},
		{"latency_sum", queries.histogramSum, sumRes},
		{"latency_count", queries.histogramCount, countRes},
		{"request_total", queries.requestTotal, reqRes},
	}
	for _, family := range families {
		query := fmt.Sprintf("count_over_time(%s[%s])", family.selector, queryDuration(step))
		provQueries[family.name+"_coverage"] = query
		res, err := c.QueryRange(ctx, query, queryStart, now, step)
		if err != nil {
			return nil, fmt.Errorf("querying %s coverage: %w", family.name, err)
		}
		coverage, err := timeBinCoverage(res, family.totals, queryStart, now, step)
		if err != nil {
			return nil, fmt.Errorf("%s coverage: %w", family.name, err)
		}
		if coverage < coverageRatio {
			coverageRatio = coverage
		}
	}

	// These raw selectors yield CPU cores and memory bytes, not the ratios
	// required by the evidence schema. Do not invent utilization without limits.
	saturation := &SaturationData{Available: false}

	bundle := &EvidenceBundle{
		SchemaVersion:  1,
		Service:        service,
		Namespace:      namespace,
		LookbackWindow: formatDuration(lookback),
		CollectedAt:    now.Format(time.RFC3339),
		CoverageRatio:  coverageRatio,
		Series: EvidenceSeries{
			LatencyHistogram: histogram,
			RequestTotal:     requestTotal,
			ErrorTotal:       errorTotal,
			Saturation:       saturation,
		},
		Provenance: EvidenceProvenance{
			PrometheusEndpoint: c.baseURL,
			QueryTimestamps: TimeRange{
				Start: start.Format(time.RFC3339),
				End:   now.Format(time.RFC3339),
			},
			Queries: provQueries,
		},
	}

	return bundle, nil
}

// ---------- internal helpers ----------

type serviceQueries struct {
	histogramBuckets  string
	histogramSum      string
	histogramCount    string
	requestTotal      string
	errorTotal        string
	cpuUtilization    string
	memoryUtilization string
}

func buildQueries(service, namespace string) serviceQueries {
	serviceLabel := names.PromLabelValue(service)
	namespaceLabel := names.PromLabelValue(namespace)
	serviceRegex := names.PromRegexLiteral(service)
	labels := fmt.Sprintf(`service="%s",namespace="%s"`, serviceLabel, namespaceLabel)
	return serviceQueries{
		histogramBuckets:  fmt.Sprintf(`http_request_duration_seconds_bucket{%s}`, labels),
		histogramSum:      fmt.Sprintf(`http_request_duration_seconds_sum{%s}`, labels),
		histogramCount:    fmt.Sprintf(`http_request_duration_seconds_count{%s}`, labels),
		requestTotal:      fmt.Sprintf(`http_requests_total{%s}`, labels),
		errorTotal:        fmt.Sprintf(`http_requests_total{%s, code=~"5.."}`, labels),
		cpuUtilization:    fmt.Sprintf(`rate(container_cpu_usage_seconds_total{namespace="%s",pod=~"%s-.*"}[5m])`, namespaceLabel, serviceRegex),
		memoryUtilization: fmt.Sprintf(`container_memory_working_set_bytes{namespace="%s",pod=~"%s-.*"}`, namespaceLabel, serviceRegex),
	}
}

func assembleSaturation(cpuRes *QueryResult, cpuErr error, memRes *QueryResult, memErr error) *SaturationData {
	sat := &SaturationData{Available: false}

	if cpuErr == nil && len(cpuRes.Data.Result) > 0 {
		samples := extractSamples(cpuRes)
		if len(samples) > 0 {
			sat.CPU = &ResourceSamples{
				MetricName: "container_cpu_usage_seconds_total",
				Samples:    samples,
			}
			sat.Available = true
		}
	}

	if memErr == nil && len(memRes.Data.Result) > 0 {
		samples := extractSamples(memRes)
		if len(samples) > 0 {
			sat.Memory = &ResourceSamples{
				MetricName: "container_memory_working_set_bytes",
				Samples:    samples,
			}
			sat.Available = true
		}
	}

	return sat
}

func extractSamples(res *QueryResult) []float64 {
	if len(res.Data.Result) == 0 {
		return nil
	}
	var samples []float64
	for _, v := range res.Data.Result[0].Values {
		samples = append(samples, v.Value)
	}
	return samples
}

func computeStep(lookback time.Duration) time.Duration {
	// Evenly partition the complete window into <=500 bins of at least60s.
	// Millisecond divisibility avoids an unobserved remainder at the window end.
	bins := int(lookback / time.Minute)
	if bins > 500 {
		bins = 500
	}
	if bins < 1 {
		bins = 1
	}
	for (lookback/time.Millisecond)%time.Duration(bins) != 0 {
		bins--
	}
	return lookback / time.Duration(bins)
}

func queryDuration(d time.Duration) string {
	if d%time.Second == 0 {
		return formatDuration(d)
	}
	return strconv.FormatInt(d.Milliseconds(), 10) + "ms"
}

func formatTime(t time.Time) string {
	return strconv.FormatFloat(float64(t.Unix())+float64(t.Nanosecond())/1e9, 'f', -1, 64)
}

func formatDuration(d time.Duration) string {
	// Only select a larger unit when it represents the entire interval exactly.
	if d%(24*time.Hour) == 0 {
		return strconv.FormatInt(int64(d/(24*time.Hour)), 10) + "d"
	}
	if d%time.Hour == 0 {
		return strconv.FormatInt(int64(d/time.Hour), 10) + "h"
	}
	if d%time.Minute == 0 {
		return strconv.FormatInt(int64(d/time.Minute), 10) + "m"
	}
	return strconv.FormatInt(int64(d/time.Second), 10) + "s"
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
