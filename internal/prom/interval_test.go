package prom

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"
)

func vectorSeries(labels map[string]string, value float64) Series {
	return Series{Metric: labels, Value: []interface{}{float64(1), strconv.FormatFloat(value, 'f', -1, 64)}}
}
func vector(series ...Series) *QueryResult {
	return &QueryResult{Status: "success", Data: QueryData{ResultType: "vector", Result: series}}
}

// The mock supplies Prometheus's reset-aware increase results, not raw lifetime
// counters. Query assertions ensure increase runs BEFORE per-instance aggregation.
func intervalServer(t *testing.T, zeroErrors, missingRequest bool) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query().Get("query")
		rows := []Series{}
		switch {
		case strings.Contains(query, "duration_seconds_bucket"):
			rows = []Series{vectorSeries(map[string]string{"le": "0.1", "instance": "a"}, 60), vectorSeries(map[string]string{"le": "1", "instance": "a"}, 90), vectorSeries(map[string]string{"le": "+Inf", "instance": "a"}, 100),
				vectorSeries(map[string]string{"le": "0.1", "instance": "b"}, 30), vectorSeries(map[string]string{"le": "1", "instance": "b"}, 45), vectorSeries(map[string]string{"le": "+Inf", "instance": "b"}, 50)}
		case strings.Contains(query, "duration_seconds_sum"):
			rows = []Series{vectorSeries(map[string]string{"instance": "a"}, 20), vectorSeries(map[string]string{"instance": "b"}, 10)}
		case strings.Contains(query, "duration_seconds_count"):
			rows = []Series{vectorSeries(map[string]string{"instance": "a"}, 100), vectorSeries(map[string]string{"instance": "b"}, 50)}
		case strings.Contains(query, `code=~"5.."`):
			if !zeroErrors {
				rows = []Series{vectorSeries(map[string]string{"instance": "a", "code": "500"}, 3), vectorSeries(map[string]string{"instance": "b", "code": "503"}, 2)}
			}
		case strings.Contains(query, "http_requests_total"):
			if !missingRequest {
				rows = []Series{vectorSeries(map[string]string{"instance": "a", "code": "200"}, 100), vectorSeries(map[string]string{"instance": "b", "code": "200"}, 45)}
				if !zeroErrors {
					rows = append(rows, vectorSeries(map[string]string{"instance": "a", "code": "500"}, 3), vectorSeries(map[string]string{"instance": "b", "code": "503"}, 2))
				}
			}
		}
		result := vector(rows...)
		if r.URL.Path == "/api/v1/query" {
			if !strings.HasPrefix(query, "increase(") || !strings.HasSuffix(query, "[7d])") && !strings.HasSuffix(query, "[5m])") {
				t.Errorf("expected per-series reset-aware interval increase, got %s", query)
			}
		} else {
			result.Data.ResultType = "matrix"
			start, _ := strconv.ParseFloat(r.URL.Query().Get("start"), 64)
			end, _ := strconv.ParseFloat(r.URL.Query().Get("end"), 64)
			step, _ := strconv.ParseFloat(r.URL.Query().Get("step"), 64)
			if strings.HasPrefix(query, "sum(rate(") {
				result.Data.Result = []Series{{Metric: map[string]string{}}}
			}
			for i := range result.Data.Result {
				result.Data.Result[i].Value = nil
				for stamp := start; stamp <= end; stamp += step {
					value := 1.0
					if strings.HasPrefix(query, "count_over_time(") {
						value = 2
					}
					result.Data.Result[i].Values = append(result.Data.Result[i].Values, SamplePair{Timestamp: stamp, Value: value})
				}
			}
		}
		w.Header().Set("Content-Type", "application/json")
		if err := json.NewEncoder(w).Encode(result); err != nil {
			t.Error(err)
		}
	}))
}

func TestIntervalCollectionAggregatesAllCodesInstancesAndBuckets(t *testing.T) {
	srv := intervalServer(t, false, false)
	defer srv.Close()
	bundle, err := NewClient(ClientConfig{BaseURL: srv.URL}).CollectEvidence(context.Background(), "api", "production", 5*time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if bundle.Series.RequestTotal.Total != 150 || bundle.Series.ErrorTotal.Total != 5 {
		t.Fatalf("not all status/instance increases counted: %+v", bundle.Series)
	}
	hist := bundle.Series.LatencyHistogram
	if hist.TotalCount != 150 || hist.Sum != 30 || len(hist.Buckets) != 2 || hist.Buckets[0].Count != 90 || hist.Buckets[1].Count != 135 {
		t.Fatalf("wrong interval histogram: %+v", hist)
	}
	if bundle.CoverageRatio != 1 {
		t.Fatalf("expected full per-series coverage, got %g", bundle.CoverageRatio)
	}
	if len(bundle.Series.RequestTotal.RateSamples) == 0 || bundle.Series.RequestTotal.RateSamples[0].Value != 1 {
		t.Fatal("throughput samples must be rates, not totals")
	}
	if !strings.HasPrefix(bundle.Provenance.Queries["request_total"], "increase(") || !strings.HasPrefix(bundle.Provenance.Queries["request_rate"], "sum(rate(") {
		t.Fatal("reset correction must precede aggregation")
	}
}

func TestNo5xxIsMeasuredZeroOnlyWithCodedRequests(t *testing.T) {
	srv := intervalServer(t, true, false)
	defer srv.Close()
	bundle, err := NewClient(ClientConfig{BaseURL: srv.URL}).CollectEvidence(context.Background(), "api", "production", 5*time.Minute)
	if err != nil || bundle.Series.ErrorTotal.Total != 0 || bundle.CoverageRatio != 1 {
		t.Fatalf("coded successful traffic must permit zero errors: %+v %v", bundle, err)
	}
	_, _, err = assembleIntervalCounters(vector(vectorSeries(map[string]string{}, 100)), vector())
	if err == nil {
		t.Fatal("uncoded traffic cannot prove zero errors")
	}
}

func TestMissingRequestsCannotBecomeHealthyZero(t *testing.T) {
	srv := intervalServer(t, true, true)
	defer srv.Close()
	if _, err := NewClient(ClientConfig{BaseURL: srv.URL}).CollectEvidence(context.Background(), "api", "production", 5*time.Minute); err == nil {
		t.Fatal("missing requests must fail")
	}
}

func TestResetCorrectedSeriesAreSummedAfterIncrease(t *testing.T) {
	// A lifetime counter 100→5→15 has reset-aware observed increase20, not15
	// and not-85. Another instance 1000→1040 contributes40. Prometheus does
	// this reset correction; the collector must sum these returned increases.
	req, failures, err := assembleIntervalCounters(vector(vectorSeries(map[string]string{"instance": "reset", "code": "200"}, 20), vectorSeries(map[string]string{"instance": "steady", "code": "200"}, 40)), vector())
	if err != nil || req.Total != 60 || failures.Total != 0 {
		t.Fatalf("lost reset-corrected series: %+v %+v %v", req, failures, err)
	}
}

func TestErrorSeriesMissingWhen5xxExistsIsRejected(t *testing.T) {
	_, _, err := assembleIntervalCounters(vector(vectorSeries(map[string]string{"code": "503"}, 3)), vector())
	if err == nil {
		t.Fatal("missing error result must not silently become zero")
	}
}

func TestCoverageCannotBeInflatedByBucketOrSeriesMultiplicity(t *testing.T) {
	start := time.Unix(1000, 0)
	end := start.Add(3 * time.Minute)
	totals := vector()
	presence := &QueryResult{Data: QueryData{ResultType: "matrix"}}
	for i := 0; i < 20; i++ {
		labels := map[string]string{"le": fmt.Sprint(i)}
		totals.Data.Result = append(totals.Data.Result, vectorSeries(labels, 100))
		row := Series{Metric: labels}
		for slot := 0; slot < 4; slot++ {
			row.Values = append(row.Values, SamplePair{Timestamp: float64(start.Unix() + int64(slot*60)), Value: 4})
		}
		if i == 19 {
			row.Values = row.Values[:1]
		}
		presence.Data.Result = append(presence.Data.Result, row)
	}
	coverage, err := timeBinCoverage(presence, totals, start, end, time.Minute)
	if err != nil || coverage != .25 {
		t.Fatalf("many full buckets inflated one missing series: %g %v", coverage, err)
	}
	presence.Data.Result = presence.Data.Result[:19]
	coverage, err = timeBinCoverage(presence, totals, start, end, time.Minute)
	if err != nil || coverage != 0 {
		t.Fatalf("entirely missing series must give zero coverage: %g %v", coverage, err)
	}
}

func TestCoverageMissingAndDuplicatePointsNeverCountTwice(t *testing.T) {
	start := time.Unix(1000, 0)
	end := start.Add(time.Minute)
	row := Series{Metric: map[string]string{}, Values: []SamplePair{{Timestamp: 1000, Value: 100}, {Timestamp: 1000, Value: 100}}}
	result := &QueryResult{Data: QueryData{ResultType: "matrix", Result: []Series{row}}}
	coverage, err := timeBinCoverage(result, vector(vectorSeries(map[string]string{}, 1)), start, end, time.Minute)
	if err != nil || coverage != .5 {
		t.Fatalf("duplicate presence samples inflated coverage: %g %v", coverage, err)
	}
}

func TestMalformedAndNonfiniteIntervalsAreRejected(t *testing.T) {
	for _, value := range []float64{math.NaN(), math.Inf(1), -1} {
		if _, err := intervalSum(vector(vectorSeries(map[string]string{}, value))); err == nil {
			t.Errorf("accepted %g", value)
		}
	}
	if _, err := assembleIntervalHistogram(vector(vectorSeries(map[string]string{"le": "0.1"}, 9)), vector(vectorSeries(nil, 1)), vector(vectorSeries(nil, 10))); err == nil {
		t.Fatal("missing +Inf must fail")
	}
}

func TestPartialPrometheusResultIsRejected(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, `{"status":"success","warnings":["partial response"],"data":{"resultType":"vector","result":[]}}`)
	}))
	defer srv.Close()
	if _, err := NewClient(ClientConfig{BaseURL: srv.URL}).InstantQuery(context.Background(), "up", time.Now()); err == nil {
		t.Fatal("partial evidence must fail")
	}
}

func TestHistogramMissingBucketInOneInstanceIsRejected(t *testing.T) {
	buckets := vector(vectorSeries(map[string]string{"instance": "a", "le": "1"}, 9), vectorSeries(map[string]string{"instance": "a", "le": "+Inf"}, 10), vectorSeries(map[string]string{"instance": "b", "le": "+Inf"}, 10))
	counts := vector(vectorSeries(map[string]string{"instance": "a"}, 10), vectorSeries(map[string]string{"instance": "b"}, 10))
	sums := vector(vectorSeries(map[string]string{"instance": "a"}, 5), vectorSeries(map[string]string{"instance": "b"}, 5))
	if _, err := assembleIntervalHistogram(buckets, sums, counts); err == nil {
		t.Fatal("partially missing histogram must fail even when total +Inf matches")
	}
}

func TestFractionalIntervalIncreasesAreNotRounded(t *testing.T) {
	req, failures, err := assembleIntervalCounters(vector(vectorSeries(map[string]string{"code": "200"}, .5), vectorSeries(map[string]string{"code": "503"}, .25)), vector(vectorSeries(map[string]string{"code": "503"}, .25)))
	if err != nil || req.Total != .75 || failures.Total != .25 {
		t.Fatalf("interval estimate was rounded: %+v %+v %v", req, failures, err)
	}
}

func TestZeroTrafficIsNotEvidenceOfHealthyService(t *testing.T) {
	if _, _, err := assembleIntervalCounters(vector(vectorSeries(map[string]string{"code": "200"}, 0)), vector()); err == nil {
		t.Fatal("zero traffic must fail rather than divide by zero or declare health")
	}
}

func TestCoverageCadencePartitionsEntireWindow(t *testing.T) {
	for _, window := range []time.Duration{125 * time.Second, 181 * time.Second, 5 * time.Minute, 7 * 24 * time.Hour, 30 * 24 * time.Hour} {
		step := computeStep(window)
		if step < time.Minute || window%step != 0 || window/step > 500 || step%time.Millisecond != 0 {
			t.Fatalf("window %s is not fully partitioned by %s", window, step)
		}
	}
	start := time.Unix(1000, 500000000)
	end := start.Add(62500 * time.Millisecond)
	row := Series{Metric: map[string]string{}, Values: []SamplePair{{Timestamp: 1000.5, Value: 2}, {Timestamp: 1063, Value: 2}}}
	coverage, err := timeBinCoverage(&QueryResult{Data: QueryData{ResultType: "matrix", Result: []Series{row}}}, vector(vectorSeries(map[string]string{}, 1)), start, end, 62500*time.Millisecond)
	if err != nil || coverage != 1 {
		t.Fatalf("fractional-second bins were not counted: %g %v", coverage, err)
	}
}

func TestWindowProvenanceDoesNotTruncatePartialDays(t *testing.T) {
	if got := formatDuration(24*time.Hour + time.Second); got != "86401s" {
		t.Fatalf("window truncated to %s", got)
	}
}

func TestSingleSampleBinsCannotClaimUsableCoverage(t *testing.T) {
	start := time.Unix(1000, 0)
	row := Series{Metric: map[string]string{}, Values: []SamplePair{{Timestamp: 1000, Value: 1}, {Timestamp: 1060, Value: 1}}}
	coverage, err := timeBinCoverage(&QueryResult{Data: QueryData{ResultType: "matrix", Result: []Series{row}}}, vector(vectorSeries(map[string]string{}, 1)), start, start.Add(time.Minute), time.Minute)
	if err != nil || coverage != 0 {
		t.Fatalf("single source samples cannot support counter rates: %g %v", coverage, err)
	}
}
