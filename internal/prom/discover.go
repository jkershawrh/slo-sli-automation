package prom

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// DiscoveredMetrics holds the metric names found for a service, along with the
// discovery source that produced them.
type DiscoveredMetrics struct {
	LatencyHistogram string
	RequestTotal     string
	ErrorTotal       string
	CPUMetric        string
	MemoryMetric     string
	Source           string // "standard", "discovered", "container-only"
}

// DiscoverMetrics queries Prometheus to find which metrics are available for a service.
func (c *Client) DiscoverMetrics(ctx context.Context, service, namespace string) (*DiscoveredMetrics, error) {
	result := &DiscoveredMetrics{}

	// Try standard metric names first
	standardPatterns := []struct {
		query string
		field *string
		name  string
	}{
		{fmt.Sprintf(`http_request_duration_seconds_bucket{service="%s",namespace="%s"}`, service, namespace), &result.LatencyHistogram, "http_request_duration_seconds"},
		{fmt.Sprintf(`http_requests_total{service="%s",namespace="%s"}`, service, namespace), &result.RequestTotal, "http_requests_total"},
		{fmt.Sprintf(`http_requests_total{service="%s",namespace="%s",code=~"5.."}`, service, namespace), &result.ErrorTotal, "http_requests_total"},
	}

	for _, p := range standardPatterns {
		qr, err := c.InstantQuery(ctx, p.query, time.Now())
		if err == nil && len(qr.Data.Result) > 0 {
			*p.field = p.name
		}
	}

	if result.LatencyHistogram != "" && result.RequestTotal != "" {
		result.Source = "standard"
		return result, nil
	}

	// Try discovery: search for any histogram with duration/latency in the name
	discoveryPatterns := []struct {
		regex string
		field *string
		typ   string
	}{
		{`{__name__=~".*duration.*bucket|.*latency.*bucket",namespace="%s"}`, &result.LatencyHistogram, "latency"},
		{`{__name__=~".*request.*total|.*http.*total",namespace="%s"}`, &result.RequestTotal, "request"},
		{`{__name__=~".*error.*total|.*fail.*total",namespace="%s"}`, &result.ErrorTotal, "error"},
	}

	for _, p := range discoveryPatterns {
		query := fmt.Sprintf(p.regex, namespace)
		qr, err := c.InstantQuery(ctx, query, time.Now())
		if err == nil && len(qr.Data.Result) > 0 {
			// Extract the metric name from the first result
			if name, ok := qr.Data.Result[0].Metric["__name__"]; ok {
				*p.field = name
				// Strip _bucket suffix for histogram base name
				if strings.HasSuffix(name, "_bucket") {
					*p.field = strings.TrimSuffix(name, "_bucket")
				}
			}
		}
	}

	if result.LatencyHistogram != "" || result.RequestTotal != "" {
		result.Source = "discovered"
	} else {
		result.Source = "container-only"
	}

	// Container metrics are always available
	result.CPUMetric = "container_cpu_usage_seconds_total"
	result.MemoryMetric = "container_memory_working_set_bytes"

	return result, nil
}
