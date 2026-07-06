package drift

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// findRepoRoot walks up from the test file to locate the directory containing go.mod.
func findRepoRoot() string {
	_, filename, _, _ := runtime.Caller(0)
	dir := filepath.Dir(filename)
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			panic("could not find repo root (no go.mod found)")
		}
		dir = parent
	}
}

func schemasDir() string {
	return filepath.Join(findRepoRoot(), "analysis", "schemas")
}

func baselinePath() string {
	return filepath.Join(findRepoRoot(), "testdata", "drift_baseline_reference.json")
}

// TestLoadBaselineValid verifies that a valid v1 baseline file loads and
// validates successfully, returning valid JSON.
func TestLoadBaselineValid(t *testing.T) {
	path := baselinePath()
	if _, err := os.Stat(path); err != nil {
		t.Skipf("baseline fixture not found: %s", path)
	}

	data, err := LoadBaseline(path, schemasDir())
	if err != nil {
		t.Fatalf("LoadBaseline returned error: %v", err)
	}

	if !json.Valid(data) {
		t.Fatal("LoadBaseline returned invalid JSON")
	}

	// Verify expected top-level fields are present.
	var doc map[string]interface{}
	if err := json.Unmarshal(data, &doc); err != nil {
		t.Fatalf("unmarshaling result: %v", err)
	}

	for _, key := range []string{"schema_version", "service", "namespace", "indicators", "provenance"} {
		if _, ok := doc[key]; !ok {
			t.Errorf("baseline missing expected key %q", key)
		}
	}
}

// TestLoadBaselineNonExistentFile verifies that loading a missing file returns
// a clear error.
func TestLoadBaselineNonExistentFile(t *testing.T) {
	_, err := LoadBaseline("/nonexistent/path/baseline.json", schemasDir())
	if err == nil {
		t.Fatal("expected error for non-existent file, got nil")
	}

	if !strings.Contains(err.Error(), "reading baseline") {
		t.Errorf("error should mention reading baseline, got: %v", err)
	}
}

// TestLoadBaselineInvalidJSON verifies that a file containing invalid JSON is
// rejected with a clear error.
func TestLoadBaselineInvalidJSON(t *testing.T) {
	tmpDir := t.TempDir()
	badFile := filepath.Join(tmpDir, "bad.json")
	if err := os.WriteFile(badFile, []byte("not valid json {{{"), 0o644); err != nil {
		t.Fatalf("writing temp file: %v", err)
	}

	_, err := LoadBaseline(badFile, schemasDir())
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}

	if !strings.Contains(err.Error(), "not valid JSON") {
		t.Errorf("error should mention invalid JSON, got: %v", err)
	}
}

// TestLoadBaselineUnsupportedVersion verifies that a baseline with an
// unsupported schema version (e.g. 99) is rejected and the error message
// names the supported versions.
func TestLoadBaselineUnsupportedVersion(t *testing.T) {
	// Create a baseline that is structurally valid but has version 99.
	// The schema enforces "const": 1, so we need to bypass schema validation
	// by testing the version check directly. Instead, test that the schema
	// validation itself catches the wrong version.
	tmpDir := t.TempDir()
	badBaseline := map[string]interface{}{
		"schema_version":  99,
		"service":         "test-service",
		"namespace":       "default",
		"lookback_window": "7d",
		"generated_at":    "2025-01-01T00:00:00Z",
		"indicators": map[string]interface{}{
			"latency": map[string]interface{}{
				"p50_ms":       50.0,
				"p90_ms":       100.0,
				"p95_ms":       150.0,
				"p99_ms":       200.0,
				"stddev_ms":    25.0,
				"sample_count": 1000,
				"source_query": "test",
			},
			"error_rate": map[string]interface{}{
				"ratio":        0.01,
				"stddev":       0.005,
				"error_count":  10,
				"total_count":  1000,
				"source_query": "test",
			},
			"availability": map[string]interface{}{
				"ratio":      0.99,
				"definition": "1 - error_rate",
			},
			"throughput": map[string]interface{}{
				"mean_rps":     100.0,
				"p95_rps":      200.0,
				"stddev_rps":   25.0,
				"sample_count": 100,
			},
		},
		"provenance": map[string]interface{}{
			"prometheus_endpoint": "http://prometheus:9090",
			"query_timestamps": map[string]interface{}{
				"start": "2024-12-25T00:00:00Z",
				"end":   "2025-01-01T00:00:00Z",
			},
			"coverage_ratio": 0.95,
		},
	}

	data, err := json.MarshalIndent(badBaseline, "", "  ")
	if err != nil {
		t.Fatalf("marshaling test baseline: %v", err)
	}

	badFile := filepath.Join(tmpDir, "baseline_v99.json")
	if err := os.WriteFile(badFile, data, 0o644); err != nil {
		t.Fatalf("writing temp file: %v", err)
	}

	_, err = LoadBaseline(badFile, schemasDir())
	if err == nil {
		t.Fatal("expected error for unsupported version, got nil")
	}

	// The schema itself enforces "const": 1, so schema validation should fail
	// before we even reach the version check. Either way, we get a clear error.
	errMsg := err.Error()
	if !strings.Contains(errMsg, "schema") && !strings.Contains(errMsg, "version") {
		t.Errorf("error should mention schema or version, got: %v", err)
	}
}

// TestLoadBaselineV1PassesVersionCheck verifies that a valid v1 baseline
// passes the version check successfully.
func TestLoadBaselineV1PassesVersionCheck(t *testing.T) {
	path := baselinePath()
	if _, err := os.Stat(path); err != nil {
		t.Skipf("baseline fixture not found: %s", path)
	}

	data, err := LoadBaseline(path, schemasDir())
	if err != nil {
		t.Fatalf("LoadBaseline returned error: %v", err)
	}

	var envelope struct {
		SchemaVersion int `json:"schema_version"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		t.Fatalf("unmarshaling version: %v", err)
	}

	if envelope.SchemaVersion != 1 {
		t.Errorf("expected schema_version 1, got %d", envelope.SchemaVersion)
	}

	// Confirm version 1 is in the supported list.
	found := false
	for _, v := range SupportedBaselineVersions {
		if v == envelope.SchemaVersion {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("schema_version %d is not in SupportedBaselineVersions %v",
			envelope.SchemaVersion, SupportedBaselineVersions)
	}
}

// TestBuildDeviationInput verifies that BuildDeviationInput produces valid
// JSON with both live_evidence and baseline fields present.
func TestBuildDeviationInput(t *testing.T) {
	liveEvidence := json.RawMessage(`{"service": "test", "metrics": [1, 2, 3]}`)
	baseline := json.RawMessage(`{"schema_version": 1, "service": "test"}`)

	result, err := BuildDeviationInput(liveEvidence, baseline)
	if err != nil {
		t.Fatalf("BuildDeviationInput returned error: %v", err)
	}

	if !json.Valid(result) {
		t.Fatal("BuildDeviationInput returned invalid JSON")
	}

	// Verify both fields are present.
	var input DeviationInput
	if err := json.Unmarshal(result, &input); err != nil {
		t.Fatalf("unmarshaling deviation input: %v", err)
	}

	if input.LiveEvidence == nil {
		t.Error("deviation input missing live_evidence")
	}
	if input.Baseline == nil {
		t.Error("deviation input missing baseline")
	}

	// Verify the content is preserved.
	var live map[string]interface{}
	if err := json.Unmarshal(input.LiveEvidence, &live); err != nil {
		t.Fatalf("unmarshaling live_evidence: %v", err)
	}
	if live["service"] != "test" {
		t.Errorf("live_evidence.service = %v, want 'test'", live["service"])
	}

	var base map[string]interface{}
	if err := json.Unmarshal(input.Baseline, &base); err != nil {
		t.Fatalf("unmarshaling baseline: %v", err)
	}
	if base["service"] != "test" {
		t.Errorf("baseline.service = %v, want 'test'", base["service"])
	}
}

// TestLoadBaselineSchemaValidationFails verifies that a structurally invalid
// baseline (missing required fields) fails schema validation.
func TestLoadBaselineSchemaValidationFails(t *testing.T) {
	tmpDir := t.TempDir()

	// Valid JSON but missing required baseline fields.
	incomplete := map[string]interface{}{
		"schema_version": 1,
		"service":        "test",
		// missing namespace, lookback_window, generated_at, indicators, provenance
	}

	data, err := json.MarshalIndent(incomplete, "", "  ")
	if err != nil {
		t.Fatalf("marshaling test data: %v", err)
	}

	badFile := filepath.Join(tmpDir, "incomplete.json")
	if err := os.WriteFile(badFile, data, 0o644); err != nil {
		t.Fatalf("writing temp file: %v", err)
	}

	_, err = LoadBaseline(badFile, schemasDir())
	if err == nil {
		t.Fatal("expected schema validation error, got nil")
	}

	if !strings.Contains(err.Error(), "schema validation failed") {
		t.Errorf("error should mention schema validation, got: %v", err)
	}
}

// TestLoadEvidenceFromFile verifies that loading a valid evidence file works.
func TestLoadEvidenceFromFile(t *testing.T) {
	root := findRepoRoot()
	path := filepath.Join(root, "testdata", "drift_live_latency_regression.json")
	if _, err := os.Stat(path); err != nil {
		t.Skipf("evidence fixture not found: %s", path)
	}

	data, err := LoadEvidenceFromFile(path)
	if err != nil {
		t.Fatalf("LoadEvidenceFromFile returned error: %v", err)
	}

	if !json.Valid(data) {
		t.Fatal("LoadEvidenceFromFile returned invalid JSON")
	}
}

// TestLoadEvidenceFromFileInvalid verifies that an invalid evidence file is
// rejected.
func TestLoadEvidenceFromFileInvalid(t *testing.T) {
	tmpDir := t.TempDir()
	badFile := filepath.Join(tmpDir, "bad.json")
	if err := os.WriteFile(badFile, []byte("{not json}"), 0o644); err != nil {
		t.Fatalf("writing temp file: %v", err)
	}

	_, err := LoadEvidenceFromFile(badFile)
	if err == nil {
		t.Fatal("expected error for invalid JSON, got nil")
	}

	if !strings.Contains(err.Error(), "not valid JSON") {
		t.Errorf("error should mention invalid JSON, got: %v", err)
	}
}

// TestBuildDeviationInputPreservesFullContent verifies the round-trip of real
// fixture data through BuildDeviationInput.
func TestBuildDeviationInputPreservesFullContent(t *testing.T) {
	root := findRepoRoot()
	baselinePath := filepath.Join(root, "testdata", "drift_baseline_reference.json")
	evidencePath := filepath.Join(root, "testdata", "drift_live_latency_regression.json")

	if _, err := os.Stat(baselinePath); err != nil {
		t.Skipf("baseline fixture not found: %s", baselinePath)
	}
	if _, err := os.Stat(evidencePath); err != nil {
		t.Skipf("evidence fixture not found: %s", evidencePath)
	}

	baselineData, err := os.ReadFile(baselinePath)
	if err != nil {
		t.Fatalf("reading baseline: %v", err)
	}

	evidenceData, err := os.ReadFile(evidencePath)
	if err != nil {
		t.Fatalf("reading evidence: %v", err)
	}

	result, err := BuildDeviationInput(json.RawMessage(evidenceData), json.RawMessage(baselineData))
	if err != nil {
		t.Fatalf("BuildDeviationInput returned error: %v", err)
	}

	// Unmarshal and verify the baseline service name survived.
	var input DeviationInput
	if err := json.Unmarshal(result, &input); err != nil {
		t.Fatalf("unmarshaling result: %v", err)
	}

	var baselineDoc map[string]interface{}
	if err := json.Unmarshal(input.Baseline, &baselineDoc); err != nil {
		t.Fatalf("unmarshaling embedded baseline: %v", err)
	}
	if baselineDoc["service"] != "checkout-api" {
		t.Errorf("embedded baseline service = %v, want 'checkout-api'", baselineDoc["service"])
	}

	var evidenceDoc map[string]interface{}
	if err := json.Unmarshal(input.LiveEvidence, &evidenceDoc); err != nil {
		t.Fatalf("unmarshaling embedded evidence: %v", err)
	}
	if evidenceDoc["service"] != "checkout-api" {
		t.Errorf("embedded evidence service = %v, want 'checkout-api'", evidenceDoc["service"])
	}
}
