package prom

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"time"
)

func instantValue(series Series) (float64, error) {
	if len(series.Value) != 2 {
		return 0, fmt.Errorf("missing instant counter increase")
	}
	text, ok := series.Value[1].(string)
	if !ok {
		return 0, fmt.Errorf("invalid instant counter value")
	}
	value, err := strconv.ParseFloat(text, 64)
	if err != nil || math.IsNaN(value) || math.IsInf(value, 0) || value < 0 {
		return 0, fmt.Errorf("counter increase must be finite and nonnegative")
	}
	return value, nil
}

func intervalSum(result *QueryResult) (float64, error) {
	if result == nil || len(result.Data.Result) == 0 {
		return 0, fmt.Errorf("required counter series is missing")
	}
	total := 0.0
	for _, series := range result.Data.Result {
		value, err := instantValue(series)
		if err != nil {
			return 0, err
		}
		total += value
	}
	if math.IsInf(total, 0) {
		return 0, fmt.Errorf("counter sum overflow")
	}
	return total, nil
}

func closeCount(a, b float64) bool {
	return math.Abs(a-b) <= 1e-6*math.Max(1, math.Max(math.Abs(a), math.Abs(b)))
}

func assembleIntervalHistogram(buckets, sums, counts *QueryResult) (HistogramData, error) {
	hd := HistogramData{MetricName: "http_request_duration_seconds"}
	var err error
	hd.TotalCount, err = intervalSum(counts)
	if err != nil {
		return hd, fmt.Errorf("histogram count: %w", err)
	}
	hd.Sum, err = intervalSum(sums)
	if err != nil {
		return hd, fmt.Errorf("histogram sum: %w", err)
	}
	if hd.TotalCount <= 0 {
		return hd, fmt.Errorf("histogram has no interval observations")
	}
	// Every histogram instance must provide the same bucket layout and matching
	// sum/count labels. An aggregate +Inf alone cannot reveal a missing bucket.
	countByInstance := map[string]float64{}
	for _, series := range counts.Data.Result {
		key := seriesIdentity(series)
		if _, exists := countByInstance[key]; exists {
			return hd, fmt.Errorf("duplicate histogram count series")
		}
		countByInstance[key], _ = instantValue(series)
	}
	sumInstances := map[string]bool{}
	for _, series := range sums.Data.Result {
		sumInstances[seriesIdentity(series)] = true
	}
	if len(sumInstances) != len(countByInstance) {
		return hd, fmt.Errorf("histogram sum/count instances differ")
	}
	for key := range countByInstance {
		if !sumInstances[key] {
			return hd, fmt.Errorf("histogram sum/count instances differ")
		}
	}
	layouts := map[string]map[float64]bool{}
	byBound := map[float64]float64{}
	infCount := 0.0
	hasInf := false
	if buckets == nil {
		return hd, fmt.Errorf("histogram buckets missing")
	}
	for _, series := range buckets.Data.Result {
		bound, err := strconv.ParseFloat(series.Metric["le"], 64)
		if err != nil || math.IsNaN(bound) || bound < 0 {
			return hd, fmt.Errorf("invalid histogram bound")
		}
		count, err := instantValue(series)
		if err != nil {
			return hd, err
		}
		labels := map[string]string{}
		for key, value := range series.Metric {
			if key != "le" {
				labels[key] = value
			}
		}
		instance := seriesIdentity(Series{Metric: labels})
		if _, exists := countByInstance[instance]; !exists {
			return hd, fmt.Errorf("histogram bucket has no matching count instance")
		}
		if layouts[instance] == nil {
			layouts[instance] = map[float64]bool{}
		}
		if layouts[instance][bound] {
			return hd, fmt.Errorf("duplicate histogram bucket series")
		}
		layouts[instance][bound] = true
		if math.IsInf(bound, 1) {
			if !closeCount(count, countByInstance[instance]) {
				return hd, fmt.Errorf("histogram instance +Inf differs from its count")
			}
			infCount += count
			hasInf = true
		} else {
			byBound[bound] += count
		}
	}
	for key := range countByInstance {
		layout := layouts[key]
		if !layout[math.Inf(1)] || len(layout) != len(byBound)+1 {
			return hd, fmt.Errorf("histogram instance has missing buckets")
		}
		for bound := range byBound {
			if !layout[bound] {
				return hd, fmt.Errorf("histogram instance has inconsistent buckets")
			}
		}
	}
	if !hasInf || !closeCount(infCount, hd.TotalCount) || len(byBound) == 0 {
		return hd, fmt.Errorf("histogram requires finite buckets and +Inf matching its interval count")
	}
	bounds := make([]float64, 0, len(byBound))
	for bound := range byBound {
		bounds = append(bounds, bound)
	}
	sort.Float64s(bounds)
	previous := 0.0
	for _, bound := range bounds {
		count := byBound[bound]
		if math.IsNaN(count) || math.IsInf(count, 0) || (count < previous && !closeCount(count, previous)) || (count > hd.TotalCount && !closeCount(count, hd.TotalCount)) {
			return hd, fmt.Errorf("histogram interval buckets are not cumulative or exceed its count")
		}
		hd.Buckets = append(hd.Buckets, HistogramBucket{Le: bound, Count: count})
		previous = count
	}
	return hd, nil
}

// Every request series must carry a valid HTTP code. Only then can an empty
// 5xx query mean measured zero errors rather than absent error instrumentation.
func assembleIntervalCounters(requests, errors *QueryResult) (CounterData, CounterData, error) {
	req := CounterData{MetricName: "http_requests_total"}
	failures := CounterData{MetricName: "http_requests_total"}
	total, err := intervalSum(requests)
	if err != nil {
		return req, failures, err
	}
	req.Total = total
	if total <= 0 {
		return req, failures, fmt.Errorf("no interval requests measured")
	}
	expectedErrors := 0.0
	for _, series := range requests.Data.Result {
		code := series.Metric["code"]
		number, err := strconv.Atoi(code)
		if err != nil || len(code) != 3 || number < 100 || number > 599 {
			return req, failures, fmt.Errorf("request series requires a valid HTTP code label to measure errors")
		}
		if number >= 500 {
			value, _ := instantValue(series)
			expectedErrors += value
		}
	}
	if errors != nil && len(errors.Data.Result) > 0 {
		failures.Total, err = intervalSum(errors)
		if err != nil {
			return req, failures, err
		}
		for _, series := range errors.Data.Result {
			number, err := strconv.Atoi(series.Metric["code"])
			if err != nil || len(series.Metric["code"]) != 3 || number < 500 || number > 599 {
				return req, failures, fmt.Errorf("error query returned a non-5xx series")
			}
		}
	}
	if !closeCount(failures.Total, expectedErrors) {
		return req, failures, fmt.Errorf("error increase disagrees with code-labeled request increases")
	}
	return req, failures, nil
}

func assembleRates(result *QueryResult) ([]RateSample, error) {
	if result == nil || result.Data.ResultType != "matrix" {
		return nil, fmt.Errorf("request rate must return a matrix")
	}
	byTime := map[float64]float64{}
	for _, series := range result.Data.Result {
		for _, sample := range series.Values {
			if math.IsNaN(sample.Value) || math.IsInf(sample.Value, 0) || sample.Value < 0 || math.IsNaN(sample.Timestamp) || math.IsInf(sample.Timestamp, 0) {
				return nil, fmt.Errorf("invalid request rate sample")
			}
			byTime[sample.Timestamp] += sample.Value
		}
	}
	if len(byTime) == 0 {
		return nil, fmt.Errorf("request rate samples missing")
	}
	timestamps := make([]float64, 0, len(byTime))
	for stamp := range byTime {
		timestamps = append(timestamps, stamp)
	}
	sort.Float64s(timestamps)
	samples := make([]RateSample, 0, len(timestamps))
	for _, stamp := range timestamps {
		samples = append(samples, RateSample{Timestamp: time.Unix(int64(stamp), 0).UTC().Format(time.RFC3339), Value: byTime[stamp]})
	}
	return samples, nil
}

func seriesIdentity(series Series) string {
	labels := map[string]string{}
	for key, value := range series.Metric {
		if key != "__name__" {
			labels[key] = value
		}
	}
	data, _ := json.Marshal(labels)
	return string(data)
}

func timeBinCoverage(result, totals *QueryResult, start, end time.Time, step time.Duration) (float64, error) {
	if result == nil || result.Data.ResultType != "matrix" {
		return 0, fmt.Errorf("expected sample-presence matrix")
	}
	expected := int(end.Sub(start)/step) + 1
	if expected < 1 || totals == nil || len(totals.Data.Result) == 0 {
		return 0, nil
	}
	observed := map[string]map[int]bool{}
	for _, series := range result.Data.Result {
		key := seriesIdentity(series)
		if _, duplicate := observed[key]; duplicate {
			return 0, fmt.Errorf("duplicate coverage series")
		}
		bins := map[int]bool{}
		for _, sample := range series.Values {
			if math.IsNaN(sample.Value) || math.IsInf(sample.Value, 0) || sample.Value < 0 || math.IsNaN(sample.Timestamp) || math.IsInf(sample.Timestamp, 0) {
				return 0, fmt.Errorf("invalid sample-presence value")
			}
			slot := int(math.Round((sample.Timestamp - (float64(start.Unix()) + float64(start.Nanosecond())/1e9)) / step.Seconds()))
			if slot >= 0 && slot < expected && math.Abs(sample.Timestamp-((float64(start.Unix())+float64(start.Nanosecond())/1e9)+float64(slot)*step.Seconds())) < 1 && sample.Value > 0 {
				bins[slot] = true
			}
		}
		observed[key] = bins
	}
	minimum := 1.0
	expectedKeys := map[string]bool{}
	for _, series := range totals.Data.Result {
		key := seriesIdentity(series)
		if expectedKeys[key] {
			return 0, fmt.Errorf("duplicate counter series")
		}
		expectedKeys[key] = true
		coverage := float64(len(observed[key])) / float64(expected)
		if coverage < minimum {
			minimum = coverage
		}
	}
	// Presence without an interval increase means too few usable counter samples.
	for key := range observed {
		if !expectedKeys[key] {
			return 0, nil
		}
	}
	return minimum, nil
}
