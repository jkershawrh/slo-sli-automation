// Package drift handles baseline loading and validation, live sampling
// orchestration, and assembly of the combined deviation input. It is the
// Go core of the drift detection pipeline (Doc 2, M1).
package drift

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/sloscope/sloscope/internal/prom"
	"github.com/sloscope/sloscope/internal/schema"
)

// SupportedBaselineVersions lists the baseline schema versions this drift
// detector supports. The drift detector refuses to run on any version not
// listed here.
var SupportedBaselineVersions = []int{1}

// LoadBaseline reads a baseline artifact from disk, validates it against
// Doc 1's frozen baseline schema, and checks that its schema version is
// supported by this drift detector. Returns the raw JSON on success.
func LoadBaseline(path string, schemasDir string) (json.RawMessage, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading baseline: %w", err)
	}

	if !json.Valid(data) {
		return nil, fmt.Errorf("baseline file %s is not valid JSON", path)
	}

	// Validate against Doc 1's frozen baseline schema.
	var doc interface{}
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("parsing baseline for validation: %w", err)
	}

	v := schema.NewValidatorFromDir(schemasDir)
	if err := v.Validate(doc, "baseline.schema.json"); err != nil {
		return nil, fmt.Errorf("baseline schema validation failed: %w", err)
	}

	// Check that the schema version is one this drift detector supports.
	var envelope struct {
		SchemaVersion int `json:"schema_version"`
	}
	if err := json.Unmarshal(data, &envelope); err != nil {
		return nil, fmt.Errorf("parsing baseline version: %w", err)
	}

	supported := false
	for _, sv := range SupportedBaselineVersions {
		if envelope.SchemaVersion == sv {
			supported = true
			break
		}
	}
	if !supported {
		return nil, fmt.Errorf(
			"unsupported baseline schema version %d (supported: %v)",
			envelope.SchemaVersion, SupportedBaselineVersions,
		)
	}

	return json.RawMessage(data), nil
}

// CollectLiveEvidence samples live telemetry from Prometheus for the given
// service over the evaluation window. Returns the evidence bundle as raw JSON.
func CollectLiveEvidence(ctx context.Context, client *prom.Client, service, namespace string, window time.Duration) (json.RawMessage, error) {
	bundle, err := client.CollectEvidence(ctx, service, namespace, window)
	if err != nil {
		return nil, fmt.Errorf("collecting live evidence: %w", err)
	}

	data, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("marshaling live evidence: %w", err)
	}

	return json.RawMessage(data), nil
}

// LoadEvidenceFromFile reads pre-collected live evidence from a JSON file.
// This supports the --evidence flag for offline testing without Prometheus.
func LoadEvidenceFromFile(path string) (json.RawMessage, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading evidence file: %w", err)
	}

	if !json.Valid(data) {
		return nil, fmt.Errorf("evidence file %s is not valid JSON", path)
	}

	return json.RawMessage(data), nil
}

// DeviationInput is the combined JSON payload sent to the Python deviation
// stage (analysis/deviation.py). It includes both the live evidence and the
// baseline artifact so the stage can compute per-indicator deviations.
type DeviationInput struct {
	LiveEvidence json.RawMessage `json:"live_evidence"`
	Baseline     json.RawMessage `json:"baseline"`
}

// BuildDeviationInput creates the combined JSON payload for the Python
// deviation stage. Both arguments must be valid JSON.
func BuildDeviationInput(liveEvidence, baseline json.RawMessage) (json.RawMessage, error) {
	input := DeviationInput{
		LiveEvidence: liveEvidence,
		Baseline:     baseline,
	}
	data, err := json.Marshal(input)
	if err != nil {
		return nil, fmt.Errorf("building deviation input: %w", err)
	}
	return json.RawMessage(data), nil
}

// FindSchemasDir locates the analysis/schemas/ directory by walking up from
// the caller's source file (useful in tests) or checking common relative
// paths from the working directory.
func FindSchemasDir() string {
	// Try from the source file location first (works in tests).
	_, filename, _, ok := runtime.Caller(0)
	if ok {
		dir := filepath.Dir(filename)
		for {
			candidate := filepath.Join(dir, "analysis", "schemas")
			if info, err := os.Stat(candidate); err == nil && info.IsDir() {
				return candidate
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}

	// Try relative to cwd.
	candidates := []string{
		"analysis/schemas",
		"../analysis/schemas",
		"../../analysis/schemas",
	}
	for _, c := range candidates {
		if info, err := os.Stat(c); err == nil && info.IsDir() {
			return c
		}
	}

	return "analysis/schemas"
}
