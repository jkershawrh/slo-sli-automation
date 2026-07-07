package prom

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"sort"
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

	now := time.Now().UTC()
	start := now.Add(-lookback)
	step := computeStep(lookback)

	queries := buildQueries(service, namespace)
	provQueries := make(map[string]string)

	// Execute latency histogram bucket query.
	provQueries["latency_histogram"] = queries.histogramBuckets
	histRes, err := c.QueryRange(ctx, queries.histogramBuckets, start, now, step)
	if err != nil {
		return nil, fmt.Errorf("querying latency histogram: %w", err)
	}

	// Execute histogram sum query.
	provQueries["latency_sum"] = queries.histogramSum
	sumRes, err := c.QueryRange(ctx, queries.histogramSum, start, now, step)
	if err != nil {
		return nil, fmt.Errorf("querying latency sum: %w", err)
	}

	// Execute histogram count query.
	provQueries["latency_count"] = queries.histogramCount
	countRes, err := c.QueryRange(ctx, queries.histogramCount, start, now, step)
	if err != nil {
		return nil, fmt.Errorf("querying latency count: %w", err)
	}

	// Execute request total query.
	provQueries["request_total"] = queries.requestTotal
	reqRes, err := c.QueryRange(ctx, queries.requestTotal, start, now, step)
	if err != nil {
		return nil, fmt.Errorf("querying request total: %w", err)
	}

	// Execute error total query.
	provQueries["error_total"] = queries.errorTotal
	errRes, err := c.QueryRange(ctx, queries.errorTotal, start, now, step)
	if err != nil {
		return nil, fmt.Errorf("querying error total: %w", err)
	}

	// Execute saturation queries (optional, may fail gracefully).
	provQueries["cpu_utilization"] = queries.cpuUtilization
	cpuRes, cpuErr := c.QueryRange(ctx, queries.cpuUtilization, start, now, step)

	provQueries["memory_utilization"] = queries.memoryUtilization
	memRes, memErr := c.QueryRange(ctx, queries.memoryUtilization, start, now, step)

	// Assemble the histogram data.
	histogram := assembleHistogram(histRes, sumRes, countRes)

	// Assemble request total.
	requestTotal := assembleCounter(reqRes, "http_requests_total")

	// Assemble error total.
	errorTotal := assembleCounter(errRes, "http_requests_total")

	// Assemble saturation data.
	saturation := assembleSaturation(cpuRes, cpuErr, memRes, memErr)

	// Compute coverage ratio: how many data points we actually got vs. expected.
	expectedPoints := int(lookback / step)
	actualPoints := countDataPoints(histRes, reqRes, errRes)
	coverageRatio := 0.0
	if expectedPoints > 0 {
		coverageRatio = math.Min(float64(actualPoints)/float64(expectedPoints*3), 1.0)
	}

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

func assembleHistogram(bucketRes, sumRes, countRes *QueryResult) HistogramData {
	hd := HistogramData{
		MetricName: "http_request_duration_seconds",
	}

	// Extract buckets: each series has an "le" label.
	type bucket struct {
		le    float64
		count float64
	}
	var buckets []bucket

	for _, s := range bucketRes.Data.Result {
		leStr, ok := s.Metric["le"]
		if !ok {
			continue
		}
		le, err := strconv.ParseFloat(leStr, 64)
		if err != nil {
			continue
		}
		// Skip +Inf buckets -- they are captured by total_count instead
		// and would break JSON marshaling.
		if math.IsInf(le, 0) {
			continue
		}
		// Use the last value in the series as the cumulative count.
		if len(s.Values) > 0 {
			buckets = append(buckets, bucket{le: le, count: s.Values[len(s.Values)-1].Value})
		}
	}

	sort.Slice(buckets, func(i, j int) bool { return buckets[i].le < buckets[j].le })

	for _, b := range buckets {
		hd.Buckets = append(hd.Buckets, HistogramBucket{Le: b.le, Count: b.count})
	}

	// Extract sum (last value).
	if len(sumRes.Data.Result) > 0 && len(sumRes.Data.Result[0].Values) > 0 {
		vals := sumRes.Data.Result[0].Values
		hd.Sum = vals[len(vals)-1].Value
	}

	// Extract count (last value).
	if len(countRes.Data.Result) > 0 && len(countRes.Data.Result[0].Values) > 0 {
		vals := countRes.Data.Result[0].Values
		hd.TotalCount = vals[len(vals)-1].Value
	}

	return hd
}

func assembleCounter(res *QueryResult, metricName string) CounterData {
	cd := CounterData{
		MetricName: metricName,
	}

	if len(res.Data.Result) == 0 {
		return cd
	}

	series := res.Data.Result[0]
	if len(series.Values) > 0 {
		cd.Total = series.Values[len(series.Values)-1].Value

		// Include rate samples from the time series.
		for _, v := range series.Values {
			cd.RateSamples = append(cd.RateSamples, RateSample{
				Timestamp: time.Unix(int64(v.Timestamp), 0).UTC().Format(time.RFC3339),
				Value:     v.Value,
			})
		}
	}

	return cd
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

func countDataPoints(results ...*QueryResult) int {
	total := 0
	for _, r := range results {
		for _, s := range r.Data.Result {
			total += len(s.Values)
		}
	}
	return total
}

func computeStep(lookback time.Duration) time.Duration {
	// Aim for ~500 data points. Prometheus has a 11,000 point limit per query.
	step := lookback / 500
	if step < 60*time.Second {
		step = 60 * time.Second
	}
	return step
}

func formatTime(t time.Time) string {
	return strconv.FormatFloat(float64(t.Unix()), 'f', -1, 64)
}

func formatDuration(d time.Duration) string {
	// Produce a clean duration string that matches the schema pattern ^[0-9]+[smhd]$.
	if h := d.Hours(); h >= 24 && int(h)%24 == 0 {
		return strconv.Itoa(int(h)/24) + "d"
	}
	if h := d.Hours(); h == float64(int(h)) {
		return strconv.Itoa(int(h)) + "h"
	}
	if m := d.Minutes(); m == float64(int(m)) {
		return strconv.Itoa(int(m)) + "m"
	}
	return strconv.Itoa(int(d.Seconds())) + "s"
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
