package render

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

const testDriftReportPath = "../../analysis/evals/recorded/drift/latency_regression_response.json"

func loadTestDriftReport(t *testing.T) json.RawMessage {
	t.Helper()
	data, err := os.ReadFile(testDriftReportPath)
	if err != nil {
		t.Fatalf("failed to load test drift report: %v", err)
	}
	return json.RawMessage(data)
}

// ---------------------------------------------------------------------------
// Drift summary renderer tests
// ---------------------------------------------------------------------------

func TestRenderDriftSummary_ProducesReadableOutputWithCorrectClassification(t *testing.T) {
	report := loadTestDriftReport(t)
	out, err := RenderDriftSummary(report)
	if err != nil {
		t.Fatalf("RenderDriftSummary error: %v", err)
	}

	// Classification should be rendered with underscores replaced by spaces.
	if !strings.Contains(out, "Classification: latency regression") {
		t.Errorf("output does not contain readable classification 'latency regression':\n%s", out)
	}
}

func TestRenderDriftSummary_ContainsServiceName(t *testing.T) {
	report := loadTestDriftReport(t)
	out, err := RenderDriftSummary(report)
	if err != nil {
		t.Fatalf("RenderDriftSummary error: %v", err)
	}

	if !strings.Contains(out, "checkout-api") {
		t.Errorf("output does not contain service name 'checkout-api':\n%s", out)
	}
}

func TestRenderDriftSummary_ContainsAllRecommendations(t *testing.T) {
	report := loadTestDriftReport(t)
	out, err := RenderDriftSummary(report)
	if err != nil {
		t.Fatalf("RenderDriftSummary error: %v", err)
	}

	// The test fixture has 2 recommendations.
	if !strings.Contains(out, "1. [high confidence]") {
		t.Errorf("output missing recommendation #1 with high confidence:\n%s", out)
	}
	if !strings.Contains(out, "2. [medium confidence]") {
		t.Errorf("output missing recommendation #2 with medium confidence:\n%s", out)
	}

	// Each recommendation should have a Rationale line.
	rationaleCount := strings.Count(out, "Rationale:")
	if rationaleCount != 2 {
		t.Errorf("expected 2 Rationale entries, got %d", rationaleCount)
	}
}

func TestRenderDriftSummary_ContainsNotAutomatedActionsDisclaimer(t *testing.T) {
	report := loadTestDriftReport(t)
	out, err := RenderDriftSummary(report)
	if err != nil {
		t.Fatalf("RenderDriftSummary error: %v", err)
	}

	if !strings.Contains(out, "not automated actions") {
		t.Errorf("output does not contain the 'not automated actions' disclaimer:\n%s", out)
	}
}

func TestRenderDriftSummary_HandlesSpecialCharacters(t *testing.T) {
	reportJSON := json.RawMessage(`{
		"schema_version": 1,
		"service": "my-service <staging> & \"test\"",
		"classification": "error_rate_elevation",
		"severity": "medium",
		"likely_cause": "Error rate increased due to upstream dependency failure (5xx > threshold & retries exhausted)",
		"recommendations": [
			{
				"action": "Check upstream logs for 5xx responses & timeouts",
				"confidence": "high",
				"rationale": "Error rate deviation of 0.05 (from 0.01 to 0.06) with <90% coverage"
			}
		]
	}`)

	out, err := RenderDriftSummary(reportJSON)
	if err != nil {
		t.Fatalf("RenderDriftSummary error: %v", err)
	}

	// Special characters should pass through unchanged in the text output.
	if !strings.Contains(out, `my-service <staging> & "test"`) {
		t.Errorf("output does not preserve special characters in service name:\n%s", out)
	}
	if !strings.Contains(out, "5xx > threshold & retries exhausted") {
		t.Errorf("output does not preserve special characters in likely cause:\n%s", out)
	}
	if !strings.Contains(out, "<90% coverage") {
		t.Errorf("output does not preserve special characters in rationale:\n%s", out)
	}
}

func TestRenderDriftSummary_InvalidJSON_ReturnsError(t *testing.T) {
	_, err := RenderDriftSummary(json.RawMessage(`{invalid`))
	if err == nil {
		t.Error("expected error for invalid JSON input")
	}
}

// ---------------------------------------------------------------------------
// Audit bundle with 4 drift sections
// ---------------------------------------------------------------------------

func TestAuditBundle_FourDriftSections_ProducesValidJSON(t *testing.T) {
	sections := map[string]json.RawMessage{
		"baseline_reference": json.RawMessage(`{"schema_version":1,"service":"checkout-api","slos":[{"sli_name":"latency_p99_ms"}]}`),
		"live_evidence":      json.RawMessage(`{"indicators":[{"name":"latency_p99_ms","value":750.0}]}`),
		"drift_signals":      json.RawMessage(`{"schema_version":1,"service":"checkout-api","indicators":[{"name":"latency_p99_ms","live_value":750.0,"baseline_value":500.0,"band_breach":true}]}`),
		"drift_report":       loadTestDriftReport(t),
	}

	bundleJSON, err := RenderAuditBundle("checkout-api", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	// Must be valid JSON.
	if !json.Valid(bundleJSON) {
		t.Error("audit bundle output is not valid JSON")
	}

	// Parse and verify structure.
	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse audit bundle: %v", err)
	}

	if len(bundle.Sections) != 4 {
		t.Errorf("expected 4 sections, got %d", len(bundle.Sections))
	}

	for _, name := range []string{"baseline_reference", "live_evidence", "drift_signals", "drift_report"} {
		if _, ok := bundle.Sections[name]; !ok {
			t.Errorf("bundle missing section %q", name)
		}
	}
}

func TestAuditBundle_FourDriftSections_HasAllContentHashes(t *testing.T) {
	sections := map[string]json.RawMessage{
		"baseline_reference": json.RawMessage(`{"schema_version":1,"service":"checkout-api"}`),
		"live_evidence":      json.RawMessage(`{"indicators":[]}`),
		"drift_signals":      json.RawMessage(`{"schema_version":1,"indicators":[]}`),
		"drift_report":       loadTestDriftReport(t),
	}

	bundleJSON, err := RenderAuditBundle("checkout-api", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse audit bundle: %v", err)
	}

	expectedSections := []string{"baseline_reference", "live_evidence", "drift_signals", "drift_report"}
	for _, name := range expectedSections {
		hash, ok := bundle.ContentHashes[name]
		if !ok {
			t.Errorf("missing content hash for section %q", name)
			continue
		}
		if len(hash) != 64 {
			t.Errorf("hash for section %q has length %d, expected 64", name, len(hash))
		}
	}
}

func TestAuditBundle_VerificationSucceeds_ForDriftBundle(t *testing.T) {
	sections := map[string]json.RawMessage{
		"baseline_reference": json.RawMessage(`{"schema_version":1,"service":"checkout-api","slos":[]}`),
		"live_evidence":      json.RawMessage(`{"indicators":[{"name":"latency_p99_ms","value":750.0}]}`),
		"drift_signals":      json.RawMessage(`{"schema_version":1,"service":"checkout-api","indicators":[{"name":"latency_p99_ms","live_value":750.0,"baseline_value":500.0}]}`),
		"drift_report":       loadTestDriftReport(t),
	}

	bundleJSON, err := RenderAuditBundle("checkout-api", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	if err := VerifyAuditBundle(bundleJSON); err != nil {
		t.Errorf("verification should succeed for valid drift bundle, got: %v", err)
	}
}

func TestAuditBundle_VerificationFails_IfDriftSignalModified(t *testing.T) {
	sections := map[string]json.RawMessage{
		"baseline_reference": json.RawMessage(`{"schema_version":1,"service":"checkout-api"}`),
		"live_evidence":      json.RawMessage(`{"indicators":[]}`),
		"drift_signals":      json.RawMessage(`{"schema_version":1,"indicators":[{"name":"latency_p99_ms","live_value":750.0}]}`),
		"drift_report":       loadTestDriftReport(t),
	}

	bundleJSON, err := RenderAuditBundle("checkout-api", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	// Tamper with the drift_signals section.
	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse bundle: %v", err)
	}
	bundle.Sections["drift_signals"] = AuditSection{
		Data: json.RawMessage(`{"schema_version":1,"indicators":[{"name":"latency_p99_ms","live_value":999.0}]}`),
	}

	tampered, _ := json.Marshal(bundle)
	if err := VerifyAuditBundle(json.RawMessage(tampered)); err == nil {
		t.Error("verification should fail for tampered drift_signals content")
	}
}
