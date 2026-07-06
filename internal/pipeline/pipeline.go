// Package pipeline orchestrates the two-stage Python analysis:
// evidence -> baseline (deterministic) -> proposal (LLM).
package pipeline

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"time"
)

// Pipeline runs Python analysis stages as subprocesses.
type Pipeline struct {
	pythonBin   string
	analysisDir string
	timeout     time.Duration
}

// PipelineConfig configures a Pipeline.
type PipelineConfig struct {
	PythonBin   string        // defaults to "python3"
	AnalysisDir string        // path to analysis/ directory
	Timeout     time.Duration // per-stage timeout, defaults to 60s
}

// New creates a Pipeline from the given configuration.
func New(cfg PipelineConfig) *Pipeline {
	if cfg.PythonBin == "" {
		cfg.PythonBin = "python3"
	}
	if cfg.Timeout == 0 {
		cfg.Timeout = 60 * time.Second
	}
	return &Pipeline{
		pythonBin:   cfg.PythonBin,
		analysisDir: cfg.AnalysisDir,
		timeout:     cfg.Timeout,
	}
}

// RunBaseline sends evidence to baseline.py and returns the computed baseline.
func (p *Pipeline) RunBaseline(ctx context.Context, evidence json.RawMessage) (json.RawMessage, error) {
	return p.runStage(ctx, "baseline.py", evidence)
}

// RunProposal sends baseline to propose.py and returns the LLM proposal.
func (p *Pipeline) RunProposal(ctx context.Context, baseline json.RawMessage) (json.RawMessage, error) {
	return p.runStage(ctx, "propose.py", baseline)
}

// RunDeviation sends the combined baseline+live_evidence payload to
// deviation.py and returns the deterministic drift-signal artifact.
func (p *Pipeline) RunDeviation(ctx context.Context, input json.RawMessage) (json.RawMessage, error) {
	return p.runStage(ctx, "deviation.py", input)
}

// RunClassification sends the drift-signal artifact to classify.py and
// returns the LLM classification and remediation report.
func (p *Pipeline) RunClassification(ctx context.Context, driftSignal json.RawMessage) (json.RawMessage, error) {
	return p.runStage(ctx, "classify.py", driftSignal)
}

// runStage executes a Python script, piping input via stdin and capturing JSON from stdout.
func (p *Pipeline) runStage(ctx context.Context, script string, input json.RawMessage) (json.RawMessage, error) {
	ctx, cancel := context.WithTimeout(ctx, p.timeout)
	defer cancel()

	scriptPath := p.analysisDir + "/" + script
	cmd := exec.CommandContext(ctx, p.pythonBin, scriptPath)
	cmd.Stdin = bytes.NewReader(input)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	// Inherit the current process environment (includes LLM_BASE_URL,
	// LLM_API_KEY, etc.) and add PYTHONPATH so analysis/ imports resolve.
	cmd.Env = append(cmd.Environ(), "PYTHONPATH="+p.analysisDir)

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("stage %s timed out after %s", script, p.timeout)
		}
		return nil, fmt.Errorf("stage %s failed: %s\nstderr: %s", script, err, stderr.String())
	}

	// Validate the output is valid JSON.
	output := stdout.Bytes()
	if !json.Valid(output) {
		return nil, fmt.Errorf("stage %s produced invalid JSON output", script)
	}

	return json.RawMessage(output), nil
}
