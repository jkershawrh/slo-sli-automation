// Package logs provides a Loki HTTP API client for collecting
// log-based evidence used in SLO baseline computation.
package logs

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"github.com/sloscope/sloscope/internal/prom"
)

// Client talks to a Loki HTTP API endpoint.
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

// CollectLogEvidence queries Loki for log data for a service.
// Returns a LogData struct ready to merge into the evidence bundle.
func (c *Client) CollectLogEvidence(ctx context.Context, service, namespace string, window time.Duration) (*prom.LogData, error) {
	end := time.Now()
	start := end.Add(-window)

	query := fmt.Sprintf(`{service="%s",namespace="%s",level="error"}`, service, namespace)
	u := fmt.Sprintf("%s/loki/api/v1/query_range?query=%s&start=%d&end=%d&limit=5000",
		c.baseURL, url.QueryEscape(query), start.UnixNano(), end.UnixNano())

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("building log request: %w", err)
	}
	if c.token != "" {
		req.Header.Set("Authorization", "Bearer "+c.token)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("querying logs: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("log query returned %d", resp.StatusCode)
	}

	var result LokiQueryResult
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("decoding log response: %w", err)
	}

	return aggregateLogs(result), nil
}

// LokiQueryResult mirrors the top-level Loki query_range response.
type LokiQueryResult struct {
	Status string   `json:"status"`
	Data   LokiData `json:"data"`
}

// LokiData holds the result type and stream data returned by a Loki query.
type LokiData struct {
	ResultType string       `json:"resultType"`
	Result     []LokiStream `json:"result"`
}

// LokiStream represents a single log stream with its label set and log entries.
type LokiStream struct {
	Stream map[string]string `json:"stream"`
	Values [][]string        `json:"values"`
}

func aggregateLogs(result LokiQueryResult) *prom.LogData {
	categories := make(map[string]int)
	totalEntries := 0

	for _, stream := range result.Data.Result {
		category := stream.Stream["error_type"]
		if category == "" {
			category = "unknown"
		}
		count := len(stream.Values)
		categories[category] += count
		totalEntries += count
	}

	ld := &prom.LogData{
		Available:    true,
		Source:       "loki",
		TotalEntries: totalEntries,
		ErrorEntries: totalEntries,
	}

	// Build breakdown sorted by count.
	var breakdown []prom.ErrorCategory
	for cat, count := range categories {
		ratio := 0.0
		if totalEntries > 0 {
			ratio = float64(count) / float64(totalEntries)
		}
		breakdown = append(breakdown, prom.ErrorCategory{
			Category: cat,
			Count:    count,
			Ratio:    ratio,
		})
	}
	sort.Slice(breakdown, func(i, j int) bool {
		return breakdown[i].Count > breakdown[j].Count
	})

	ld.ErrorBreakdown = breakdown

	// Build rate by category.
	ld.ErrorRateByCategory = make(map[string]float64)
	for _, cat := range breakdown {
		ld.ErrorRateByCategory[cat.Category] = cat.Ratio
	}

	return ld
}
