package render

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"strings"
	"testing"
)

const testProposalPath = "../../analysis/evals/recorded/web_api_baseline_response.json"

func loadTestProposal(t *testing.T) json.RawMessage {
	t.Helper()
	data, err := os.ReadFile(testProposalPath)
	if err != nil {
		t.Fatalf("failed to load test proposal: %v", err)
	}
	return json.RawMessage(data)
}

// ---------------------------------------------------------------------------
// OpenSLO renderer tests
// ---------------------------------------------------------------------------

func TestRenderOpenSLO_ValidYAML_HasApiVersion(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderOpenSLO(proposal)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	if !strings.Contains(out, "apiVersion: openslo/v1") {
		t.Error("output does not contain apiVersion: openslo/v1")
	}
}

func TestRenderOpenSLO_ContainsServiceName(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderOpenSLO(proposal)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	if !strings.Contains(out, "service: checkout-api") {
		t.Errorf("output does not contain service name 'checkout-api':\n%s", out)
	}
}

func TestRenderOpenSLO_ContainsSLONames(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderOpenSLO(proposal)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	expectedNames := []string{"request_latency_p99", "service_availability"}
	for _, name := range expectedNames {
		if !strings.Contains(out, name) {
			t.Errorf("output does not contain SLO name %q", name)
		}
	}
}

func TestRenderOpenSLO_HasAlertPolicies(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderOpenSLO(proposal)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	if !strings.Contains(out, "alertPolicies:") {
		t.Error("output does not contain alertPolicies section")
	}
	// Should have both critical and warning severities
	if !strings.Contains(out, "severity: critical") {
		t.Error("output does not contain severity: critical")
	}
	if !strings.Contains(out, "severity: warning") {
		t.Error("output does not contain severity: warning")
	}
}

func TestRenderOpenSLO_SanitizesSpecialCharacters(t *testing.T) {
	proposalJSON := json.RawMessage(`{
		"schema_version": 1,
		"service": "My Service! @#$",
		"baseline_schema_version": 1,
		"slos": [{
			"sli_name": "Error Rate (5xx)",
			"sli_type": "error_rate",
			"sli_definition": "test",
			"target": 0.99,
			"target_unit": "ratio",
			"error_budget_percent": 1.0,
			"burn_rate_policy": {"windows": []},
			"rationale": "test"
		}]
	}`)
	out, err := RenderOpenSLO(proposalJSON)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	// The metadata name fields should be sanitized: only lowercase alphanumeric and hyphens.
	// Extract all "name:" lines under metadata to verify sanitization.
	lines := strings.Split(out, "\n")
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "name: ") {
			nameVal := strings.TrimPrefix(trimmed, "name: ")
			for _, c := range nameVal {
				if !((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-') {
					t.Errorf("metadata name %q contains unsanitized character %q", nameVal, string(c))
				}
			}
		}
	}
	if !strings.Contains(out, "my-service") {
		t.Errorf("expected sanitized service name 'my-service' in output:\n%s", out)
	}
	if !strings.Contains(out, "error-rate-5xx") {
		t.Errorf("expected sanitized SLI name 'error-rate-5xx' in output:\n%s", out)
	}
}

func TestRenderOpenSLO_MultipleSLOs_SeparatedByDocumentMarker(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderOpenSLO(proposal)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	// The test proposal has 2 SLOs, so there should be one "---" separator
	count := strings.Count(out, "---\n")
	if count != 1 {
		t.Errorf("expected 1 document separator (---), got %d", count)
	}
	// Should contain two apiVersion lines
	apiVersionCount := strings.Count(out, "apiVersion: openslo/v1")
	if apiVersionCount != 2 {
		t.Errorf("expected 2 apiVersion declarations, got %d", apiVersionCount)
	}
}

func TestRenderOpenSLO_LatencySLO_HasTargetAndValue(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderOpenSLO(proposal)
	if err != nil {
		t.Fatalf("RenderOpenSLO error: %v", err)
	}
	// Latency SLO should have op: lte and a value field
	if !strings.Contains(out, "op: lte") {
		t.Error("latency SLO output missing 'op: lte'")
	}
	if !strings.Contains(out, "value: 595") {
		t.Error("latency SLO output missing 'value: 595'")
	}
}

func TestRenderOpenSLO_InvalidJSON_ReturnsError(t *testing.T) {
	_, err := RenderOpenSLO(json.RawMessage(`{invalid`))
	if err == nil {
		t.Error("expected error for invalid JSON input")
	}
}

// ---------------------------------------------------------------------------
// Prometheus rules renderer tests
// ---------------------------------------------------------------------------

func TestRenderPrometheusRules_HasGroupsTopLevel(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderPrometheusRules(proposal, "checkout-api")
	if err != nil {
		t.Fatalf("RenderPrometheusRules error: %v", err)
	}
	if !strings.HasPrefix(out, "groups:\n") {
		t.Errorf("output does not start with 'groups:':\n%s", out[:min(len(out), 100)])
	}
}

func TestRenderPrometheusRules_ContainsRecordingRules(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderPrometheusRules(proposal, "checkout-api")
	if err != nil {
		t.Fatalf("RenderPrometheusRules error: %v", err)
	}
	// Should have recording rules for both SLOs
	if !strings.Contains(out, "record: slo:request-latency-p99:latency_ratio") {
		t.Error("missing recording rule for latency SLO")
	}
	if !strings.Contains(out, "record: slo:service-availability:error_ratio") {
		t.Error("missing recording rule for availability SLO")
	}
}

func TestRenderPrometheusRules_ContainsAlertingRulesWithSeverity(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderPrometheusRules(proposal, "checkout-api")
	if err != nil {
		t.Fatalf("RenderPrometheusRules error: %v", err)
	}
	if !strings.Contains(out, "severity: critical") {
		t.Error("output missing severity: critical label")
	}
	if !strings.Contains(out, "severity: warning") {
		t.Error("output missing severity: warning label")
	}
}

func TestRenderPrometheusRules_CorrectBurnRateThresholds(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderPrometheusRules(proposal, "checkout-api")
	if err != nil {
		t.Fatalf("RenderPrometheusRules error: %v", err)
	}
	// The test proposal has burn rates of 14.4 and 6.0
	if !strings.Contains(out, "14.4") {
		t.Error("output missing burn rate threshold 14.4")
	}
	if !strings.Contains(out, "6") {
		t.Error("output missing burn rate threshold 6")
	}
}

func TestRenderPrometheusRules_MultiWindowConditions(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderPrometheusRules(proposal, "checkout-api")
	if err != nil {
		t.Fatalf("RenderPrometheusRules error: %v", err)
	}
	// Multi-window requires both long and short windows connected with "and"
	if !strings.Contains(out, "and") {
		t.Error("output missing 'and' for multi-window burn rate conditions")
	}
	// Should reference both 1h (long) and 5m (short) windows
	if !strings.Contains(out, "1h") {
		t.Error("output missing long window '1h'")
	}
	if !strings.Contains(out, "5m") {
		t.Error("output missing short window '5m'")
	}
}

func TestRenderPrometheusRules_RecordingRulesReferenceService(t *testing.T) {
	proposal := loadTestProposal(t)
	out, err := RenderPrometheusRules(proposal, "checkout-api")
	if err != nil {
		t.Fatalf("RenderPrometheusRules error: %v", err)
	}
	if !strings.Contains(out, `service="checkout-api"`) {
		t.Errorf("recording rules do not reference service 'checkout-api':\n%s", out)
	}
}

func TestRenderPrometheusRules_InvalidJSON_ReturnsError(t *testing.T) {
	_, err := RenderPrometheusRules(json.RawMessage(`{bad`), "svc")
	if err == nil {
		t.Error("expected error for invalid JSON input")
	}
}

// ---------------------------------------------------------------------------
// Audit bundle renderer tests
// ---------------------------------------------------------------------------

func TestRenderAuditBundle_ContainsAllSections(t *testing.T) {
	sections := map[string]json.RawMessage{
		"evidence": json.RawMessage(`{"foo":"bar"}`),
		"baseline": json.RawMessage(`{"baz":1}`),
		"proposal": json.RawMessage(`{"qux":true}`),
	}

	bundleJSON, err := RenderAuditBundle("test-service", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse audit bundle: %v", err)
	}

	for _, name := range []string{"evidence", "baseline", "proposal"} {
		if _, ok := bundle.Sections[name]; !ok {
			t.Errorf("bundle missing section %q", name)
		}
	}
}

func TestRenderAuditBundle_ContentHashesAreSHA256Hex(t *testing.T) {
	sections := map[string]json.RawMessage{
		"evidence": json.RawMessage(`{"foo":"bar"}`),
		"baseline": json.RawMessage(`{"baz":1}`),
		"proposal": json.RawMessage(`{"qux":true}`),
	}

	bundleJSON, err := RenderAuditBundle("test-service", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse audit bundle: %v", err)
	}

	for name, hashStr := range bundle.ContentHashes {
		// SHA-256 hex string is 64 characters
		if len(hashStr) != 64 {
			t.Errorf("hash for section %q has length %d, expected 64", name, len(hashStr))
		}
		// Must be valid hex
		if _, err := hex.DecodeString(hashStr); err != nil {
			t.Errorf("hash for section %q is not valid hex: %v", name, err)
		}
	}
}

func TestVerifyAuditBundle_ValidBundle_Succeeds(t *testing.T) {
	sections := map[string]json.RawMessage{
		"evidence": json.RawMessage(`{"data":"evidence_data"}`),
		"baseline": json.RawMessage(`{"data":"baseline_data"}`),
		"proposal": json.RawMessage(`{"data":"proposal_data"}`),
	}

	bundleJSON, err := RenderAuditBundle("test-service", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	if err := VerifyAuditBundle(bundleJSON); err != nil {
		t.Errorf("verification should succeed for valid bundle, got: %v", err)
	}
}

func TestVerifyAuditBundle_ModifiedContent_Fails(t *testing.T) {
	sections := map[string]json.RawMessage{
		"evidence": json.RawMessage(`{"data":"original"}`),
	}

	bundleJSON, err := RenderAuditBundle("test-service", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	// Tamper with the content
	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse bundle: %v", err)
	}
	bundle.Sections["evidence"] = AuditSection{Data: json.RawMessage(`{"data":"tampered"}`)}

	tampered, _ := json.Marshal(bundle)
	if err := VerifyAuditBundle(json.RawMessage(tampered)); err == nil {
		t.Error("verification should fail for tampered content")
	}
}

func TestVerifyAuditBundle_MissingHashForSection_Fails(t *testing.T) {
	// Build a bundle manually with a section that has no corresponding hash
	bundle := AuditBundle{
		SchemaVersion: 1,
		Service:       "test",
		Sections: map[string]AuditSection{
			"evidence": {Data: json.RawMessage(`{"foo":"bar"}`)},
		},
		ContentHashes: map[string]string{
			// no hash for "evidence"
		},
	}

	bundleJSON, _ := json.Marshal(bundle)
	if err := VerifyAuditBundle(json.RawMessage(bundleJSON)); err == nil {
		t.Error("verification should fail when section has no content hash")
	}
}

func TestVerifyAuditBundle_OrphanedHash_Fails(t *testing.T) {
	// Build a bundle with a hash for a section that does not exist
	hash := sha256.Sum256([]byte(`{"foo":"bar"}`))
	bundle := AuditBundle{
		SchemaVersion: 1,
		Service:       "test",
		Sections:      map[string]AuditSection{},
		ContentHashes: map[string]string{
			"phantom": hex.EncodeToString(hash[:]),
		},
	}

	bundleJSON, _ := json.Marshal(bundle)
	if err := VerifyAuditBundle(json.RawMessage(bundleJSON)); err == nil {
		t.Error("verification should fail when hash exists for non-existent section")
	}
}

func TestRenderAuditBundle_EmptySections(t *testing.T) {
	sections := map[string]json.RawMessage{}

	bundleJSON, err := RenderAuditBundle("empty-service", sections)
	if err != nil {
		t.Fatalf("RenderAuditBundle error: %v", err)
	}

	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		t.Fatalf("failed to parse audit bundle: %v", err)
	}

	if len(bundle.Sections) != 0 {
		t.Errorf("expected 0 sections, got %d", len(bundle.Sections))
	}
	if len(bundle.ContentHashes) != 0 {
		t.Errorf("expected 0 content hashes, got %d", len(bundle.ContentHashes))
	}
}

func TestRenderAuditBundle_Deterministic(t *testing.T) {
	sections := map[string]json.RawMessage{
		"alpha":   json.RawMessage(`{"a":1}`),
		"beta":    json.RawMessage(`{"b":2}`),
		"gamma":   json.RawMessage(`{"c":3}`),
	}

	result1, err := RenderAuditBundle("test-service", sections)
	if err != nil {
		t.Fatalf("first render failed: %v", err)
	}

	result2, err := RenderAuditBundle("test-service", sections)
	if err != nil {
		t.Fatalf("second render failed: %v", err)
	}

	if string(result1) != string(result2) {
		t.Error("RenderAuditBundle is not deterministic: two calls with same input produced different output")
	}
}
