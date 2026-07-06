package pipeline

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/sloscope/sloscope/internal/schema"
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

// newTestPipeline returns a Pipeline configured for integration tests.
func newTestPipeline(timeout time.Duration) *Pipeline {
	root := findRepoRoot()
	if timeout == 0 {
		timeout = 30 * time.Second
	}
	return New(PipelineConfig{
		AnalysisDir: filepath.Join(root, "analysis"),
		Timeout:     timeout,
	})
}

// loadFixture reads a JSON fixture file from testdata/.
func loadFixture(t *testing.T, name string) json.RawMessage {
	t.Helper()
	root := findRepoRoot()
	path := filepath.Join(root, "testdata", name)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("loading fixture %s: %v", name, err)
	}
	return json.RawMessage(data)
}

// TestRunBaselineValid verifies that baseline.py produces valid JSON from a
// well-formed evidence fixture.
func TestRunBaselineValid(t *testing.T) {
	p := newTestPipeline(0)
	evidence := loadFixture(t, "evidence_checkout_api.json")

	result, err := p.RunBaseline(context.Background(), evidence)
	if err != nil {
		t.Fatalf("RunBaseline returned error: %v", err)
	}

	if !json.Valid(result) {
		t.Fatal("RunBaseline output is not valid JSON")
	}

	// Verify the output has expected top-level fields.
	var baseline map[string]interface{}
	if err := json.Unmarshal(result, &baseline); err != nil {
		t.Fatalf("unmarshaling baseline: %v", err)
	}

	for _, key := range []string{"schema_version", "service", "namespace", "indicators", "provenance"} {
		if _, ok := baseline[key]; !ok {
			t.Errorf("baseline missing expected key %q", key)
		}
	}

	// Verify the service name made it through.
	if svc, ok := baseline["service"].(string); !ok || svc != "checkout-api" {
		t.Errorf("expected service=checkout-api, got %v", baseline["service"])
	}
}

// TestRunBaselineSchemaValidation verifies the baseline output validates against
// the baseline JSON schema using the Go schema validator.
func TestRunBaselineSchemaValidation(t *testing.T) {
	root := findRepoRoot()
	p := newTestPipeline(0)
	evidence := loadFixture(t, "evidence_checkout_api.json")

	result, err := p.RunBaseline(context.Background(), evidence)
	if err != nil {
		t.Fatalf("RunBaseline returned error: %v", err)
	}

	// Unmarshal into a generic interface{} for schema validation.
	var baselineDoc interface{}
	if err := json.Unmarshal(result, &baselineDoc); err != nil {
		t.Fatalf("unmarshaling baseline for schema validation: %v", err)
	}

	// Validate against the baseline schema using the project's validator.
	schemasDir := filepath.Join(root, "analysis", "schemas")
	v := schema.NewValidatorFromDir(schemasDir)
	if err := v.Validate(baselineDoc, "baseline.schema.json"); err != nil {
		t.Errorf("baseline output failed schema validation: %v", err)
	}
}

// TestRunStageNonExistentScript verifies that running a non-existent script
// returns a clear error message.
func TestRunStageNonExistentScript(t *testing.T) {
	root := findRepoRoot()
	p := New(PipelineConfig{
		AnalysisDir: filepath.Join(root, "analysis"),
		Timeout:     5 * time.Second,
	})

	input := json.RawMessage(`{}`)
	_, err := p.runStage(context.Background(), "nonexistent.py", input)
	if err == nil {
		t.Fatal("expected error for non-existent script, got nil")
	}

	if !strings.Contains(err.Error(), "nonexistent.py") {
		t.Errorf("error should mention the script name, got: %v", err)
	}
}

// TestRunStageNonZeroExit verifies that a script exiting non-zero returns
// the stderr content in the error message.
func TestRunStageNonZeroExit(t *testing.T) {
	// Create a temporary Python script that prints to stderr and exits 1.
	tmpDir := t.TempDir()
	script := filepath.Join(tmpDir, "fail.py")
	err := os.WriteFile(script, []byte(`
import sys
print("something went wrong", file=sys.stderr)
sys.exit(1)
`), 0o644)
	if err != nil {
		t.Fatalf("writing temp script: %v", err)
	}

	p := New(PipelineConfig{
		AnalysisDir: tmpDir,
		Timeout:     5 * time.Second,
	})

	input := json.RawMessage(`{}`)
	_, err = p.runStage(context.Background(), "fail.py", input)
	if err == nil {
		t.Fatal("expected error from failing script, got nil")
	}

	if !strings.Contains(err.Error(), "something went wrong") {
		t.Errorf("error should include stderr content, got: %v", err)
	}
	if !strings.Contains(err.Error(), "fail.py") {
		t.Errorf("error should mention the script name, got: %v", err)
	}
}

// TestRunStageTimeout verifies that the per-stage timeout is enforced.
func TestRunStageTimeout(t *testing.T) {
	// Create a temporary Python script that sleeps longer than the timeout.
	tmpDir := t.TempDir()
	script := filepath.Join(tmpDir, "slow.py")
	err := os.WriteFile(script, []byte(`
import time
time.sleep(30)
`), 0o644)
	if err != nil {
		t.Fatalf("writing temp script: %v", err)
	}

	p := New(PipelineConfig{
		AnalysisDir: tmpDir,
		Timeout:     500 * time.Millisecond, // very short timeout
	})

	input := json.RawMessage(`{}`)
	start := time.Now()
	_, err = p.runStage(context.Background(), "slow.py", input)
	elapsed := time.Since(start)

	if err == nil {
		t.Fatal("expected timeout error, got nil")
	}

	if !strings.Contains(err.Error(), "timed out") {
		t.Errorf("error should mention timeout, got: %v", err)
	}

	// The timeout should fire well before the 30s sleep completes.
	if elapsed > 5*time.Second {
		t.Errorf("timeout took too long: %v (expected ~500ms)", elapsed)
	}
}
