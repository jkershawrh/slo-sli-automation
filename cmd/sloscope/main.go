package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/sloscope/sloscope/internal/config"
	"github.com/sloscope/sloscope/internal/drift"
	"github.com/sloscope/sloscope/internal/logs"
	"github.com/sloscope/sloscope/internal/pipeline"
	"github.com/sloscope/sloscope/internal/prom"
	"github.com/sloscope/sloscope/internal/render"
	"github.com/sloscope/sloscope/internal/traces"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: sloscope <command> [flags]")
		fmt.Fprintln(os.Stderr, "commands: generate, drift")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "generate":
		if err := runGenerate(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}
	case "drift":
		if err := runDrift(os.Args[2:]); err != nil {
			fmt.Fprintf(os.Stderr, "error: %v\n", err)
			os.Exit(1)
		}
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", os.Args[1])
		fmt.Fprintln(os.Stderr, "commands: generate, drift")
		os.Exit(1)
	}
}

// parseLookback parses a duration string like "7d", "24h", "30m" into a time.Duration.
func parseLookback(s string) (time.Duration, error) {
	if len(s) < 2 {
		return 0, fmt.Errorf("invalid lookback %q: too short", s)
	}
	unit := s[len(s)-1]
	numStr := s[:len(s)-1]

	var n int
	if _, err := fmt.Sscanf(numStr, "%d", &n); err != nil {
		return 0, fmt.Errorf("invalid lookback %q: %w", s, err)
	}

	switch unit {
	case 's':
		return time.Duration(n) * time.Second, nil
	case 'm':
		return time.Duration(n) * time.Minute, nil
	case 'h':
		return time.Duration(n) * time.Hour, nil
	case 'd':
		return time.Duration(n) * 24 * time.Hour, nil
	default:
		return 0, fmt.Errorf("invalid lookback %q: unknown unit %q (use s/m/h/d)", s, string(unit))
	}
}

// findAnalysisDir locates the analysis/ directory relative to the executable
// or falling back to the current working directory.
func findAnalysisDir() (string, error) {
	// Try relative to the executable first.
	exe, err := os.Executable()
	if err == nil {
		candidate := filepath.Join(filepath.Dir(exe), "..", "..", "analysis")
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return filepath.Abs(candidate)
		}
	}

	// Try relative to the current working directory.
	cwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("could not determine working directory: %w", err)
	}

	candidate := filepath.Join(cwd, "analysis")
	if info, err := os.Stat(candidate); err == nil && info.IsDir() {
		return candidate, nil
	}

	return "", fmt.Errorf("could not find analysis/ directory (checked relative to executable and cwd)")
}

func runGenerate(args []string) error {
	fs := flag.NewFlagSet("generate", flag.ContinueOnError)
	service := fs.String("service", "", "service name")
	namespace := fs.String("namespace", "", "Kubernetes namespace")
	lookback := fs.String("lookback", "7d", "lookback duration (e.g. 7d, 24h)")
	out := fs.String("out", "", "output directory")
	dryRun := fs.Bool("dry-run", false, "validate and render without calling the LLM")
	evidencePath := fs.String("evidence", "", "path to existing evidence JSON file (skips Prometheus collection)")
	contextType := fs.String("type", "service", "context type: service or infra")
	maturityTier := fs.String("maturity", "growing", "maturity tier: new, growing, or mature")

	if err := fs.Parse(args); err != nil {
		return err
	}

	cfg, err := config.Load(*dryRun)
	if err != nil {
		return fmt.Errorf("loading config: %w", err)
	}

	// Export context type and maturity tier for pipeline stages.
	os.Setenv("SLOSCOPE_CONTEXT_TYPE", *contextType)
	os.Setenv("SLOSCOPE_MATURITY_TIER", *maturityTier)

	// Default output directory.
	outDir := *out
	if outDir == "" {
		outDir = "."
	}

	// Ensure the output directory exists.
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return fmt.Errorf("creating output directory: %w", err)
	}

	ctx := context.Background()

	// ---- Step 1: Obtain evidence ----
	var evidence json.RawMessage

	switch {
	case *evidencePath != "":
		// Load evidence from the provided file.
		data, err := os.ReadFile(*evidencePath)
		if err != nil {
			return fmt.Errorf("reading evidence file: %w", err)
		}
		if !json.Valid(data) {
			return fmt.Errorf("evidence file %s is not valid JSON", *evidencePath)
		}
		evidence = json.RawMessage(data)
		fmt.Printf("Loaded evidence from %s\n", *evidencePath)

	case cfg.PromURL != "":
		// Collect evidence from Prometheus.
		if *service == "" {
			return fmt.Errorf("--service is required when collecting from Prometheus")
		}
		ns := *namespace
		if ns == "" {
			ns = "default"
		}

		lb, err := parseLookback(*lookback)
		if err != nil {
			return err
		}

		client := prom.NewClient(prom.ClientConfig{
			BaseURL: cfg.PromURL,
			Token:   cfg.PromToken,
		})

		fmt.Printf("Collecting evidence from %s for %s/%s (lookback: %s)...\n",
			cfg.PromURL, ns, *service, *lookback)

		bundle, err := client.CollectEvidence(ctx, *service, ns, lb)
		if err != nil {
			return fmt.Errorf("collecting evidence: %w", err)
		}

		// Enrich evidence with traces if TEMPO_URL is configured.
		if cfg.TempoURL != "" {
			fmt.Printf("Collecting trace evidence from %s...\n", cfg.TempoURL)
			traceClient := traces.NewClient(traces.ClientConfig{
				BaseURL: cfg.TempoURL,
				Token:   cfg.TempoToken,
			})
			traceData, err := traceClient.CollectTraceEvidence(ctx, *service, lb)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: trace collection failed: %v\n", err)
			} else {
				bundle.Series.Traces = traceData
				bundle.SchemaVersion = 2
				fmt.Println("Trace evidence collected")
			}
		}

		// Enrich evidence with logs if LOKI_URL is configured.
		if cfg.LokiURL != "" {
			fmt.Printf("Collecting log evidence from %s...\n", cfg.LokiURL)
			logClient := logs.NewClient(logs.ClientConfig{
				BaseURL: cfg.LokiURL,
				Token:   cfg.LokiToken,
			})
			logData, err := logClient.CollectLogEvidence(ctx, *service, ns, lb)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: log collection failed: %v\n", err)
			} else {
				bundle.Series.Logs = logData
				bundle.SchemaVersion = 2
				fmt.Println("Log evidence collected")
			}
		}

		evidence, err = json.MarshalIndent(bundle, "", "  ")
		if err != nil {
			return fmt.Errorf("marshaling evidence: %w", err)
		}
		fmt.Println("Evidence collected successfully")

	default:
		// Try to load evidence from the output directory.
		existingPath := filepath.Join(outDir, "evidence.json")
		data, err := os.ReadFile(existingPath)
		if err != nil {
			return fmt.Errorf("no evidence source: set PROM_URL, use --evidence, or place evidence.json in --out directory")
		}
		if !json.Valid(data) {
			return fmt.Errorf("existing evidence file %s is not valid JSON", existingPath)
		}
		evidence = json.RawMessage(data)
		fmt.Printf("Loaded existing evidence from %s\n", existingPath)
	}

	// Save evidence artifact.
	evidenceFile := filepath.Join(outDir, "evidence.json")
	if err := os.WriteFile(evidenceFile, evidence, 0o644); err != nil {
		return fmt.Errorf("writing evidence: %w", err)
	}

	// ---- Step 2: Run baseline stage ----
	analysisDir, err := findAnalysisDir()
	if err != nil {
		return err
	}

	pipe := pipeline.New(pipeline.PipelineConfig{
		AnalysisDir: analysisDir,
	})

	fmt.Println("Running baseline analysis...")
	baseline, err := pipe.RunBaseline(ctx, evidence)
	if err != nil {
		return fmt.Errorf("baseline stage: %w", err)
	}

	// Save baseline artifact.
	baselineFile := filepath.Join(outDir, "baseline.json")
	if err := os.WriteFile(baselineFile, baseline, 0o644); err != nil {
		return fmt.Errorf("writing baseline: %w", err)
	}
	fmt.Printf("Baseline written to %s\n", baselineFile)

	// ---- Step 3: Proposal stage (skip if dry-run) ----
	if *dryRun {
		fmt.Println("\n--- Baseline (dry-run) ---")
		fmt.Println(string(baseline))
		fmt.Println("\nDry-run complete. Skipping proposal stage.")
		return nil
	}

	fmt.Println("Running proposal analysis...")
	proposal, err := pipe.RunProposal(ctx, baseline)
	if err != nil {
		return fmt.Errorf("proposal stage: %w", err)
	}

	// Save proposal artifact.
	proposalFile := filepath.Join(outDir, "proposal.json")
	if err := os.WriteFile(proposalFile, proposal, 0o644); err != nil {
		return fmt.Errorf("writing proposal: %w", err)
	}
	fmt.Printf("Proposal written to %s\n", proposalFile)

	// ---- Step 4: Render outputs ----

	// Render OpenSLO YAML.
	fmt.Println("Rendering OpenSLO YAML...")
	opensloYAML, err := render.RenderOpenSLO(proposal)
	if err != nil {
		return fmt.Errorf("rendering OpenSLO: %w", err)
	}
	opensloFile := filepath.Join(outDir, "openslo.yaml")
	if err := os.WriteFile(opensloFile, []byte(opensloYAML), 0o644); err != nil {
		return fmt.Errorf("writing OpenSLO YAML: %w", err)
	}
	fmt.Printf("OpenSLO YAML written to %s\n", opensloFile)

	// Render Prometheus rules.
	fmt.Println("Rendering Prometheus rules...")
	svcName := *service
	if svcName == "" {
		svcName = "unknown"
	}
	promRules, err := render.RenderPrometheusRules(proposal, svcName)
	if err != nil {
		return fmt.Errorf("rendering Prometheus rules: %w", err)
	}
	promFile := filepath.Join(outDir, "prometheus-rules.yaml")
	if err := os.WriteFile(promFile, []byte(promRules), 0o644); err != nil {
		return fmt.Errorf("writing Prometheus rules: %w", err)
	}
	fmt.Printf("Prometheus rules written to %s\n", promFile)

	// Render audit bundle.
	fmt.Println("Rendering audit bundle...")
	sections := map[string]json.RawMessage{
		"evidence": evidence,
		"baseline": baseline,
		"proposal": proposal,
	}
	auditBundle, err := render.RenderAuditBundle(svcName, sections)
	if err != nil {
		return fmt.Errorf("rendering audit bundle: %w", err)
	}
	auditFile := filepath.Join(outDir, "audit-bundle.json")
	if err := os.WriteFile(auditFile, auditBundle, 0o644); err != nil {
		return fmt.Errorf("writing audit bundle: %w", err)
	}
	fmt.Printf("Audit bundle written to %s\n", auditFile)

	// ---- Summary ----
	fmt.Printf("\nGeneration complete. Artifacts saved to %s/:\n", outDir)
	fmt.Println("  - evidence.json")
	fmt.Println("  - baseline.json")
	fmt.Println("  - proposal.json")
	fmt.Println("  - openslo.yaml")
	fmt.Println("  - prometheus-rules.yaml")
	fmt.Println("  - audit-bundle.json")

	return nil
}

func runDrift(args []string) error {
	fs := flag.NewFlagSet("drift", flag.ContinueOnError)
	service := fs.String("service", "", "service name (required)")
	namespace := fs.String("namespace", "default", "Kubernetes namespace")
	baselinePath := fs.String("baseline", "", "path to baseline.json artifact (required)")
	window := fs.String("window", "1h", "evaluation window duration (e.g. 1h, 30m)")
	out := fs.String("out", "", "output directory for drift artifacts")
	dryRun := fs.Bool("dry-run", false, "run deviation only, skip LLM classification")
	evidencePath := fs.String("evidence", "", "path to pre-collected live evidence JSON (skips Prometheus)")
	contextType := fs.String("type", "service", "context type: service or infra")
	maturityTier := fs.String("maturity", "growing", "maturity tier: new, growing, or mature")

	if err := fs.Parse(args); err != nil {
		return err
	}

	// Validate required flags.
	if *service == "" {
		return fmt.Errorf("--service is required")
	}
	if *baselinePath == "" {
		return fmt.Errorf("--baseline is required")
	}

	// ---- Step 1: Load config ----
	cfg, err := config.Load(*dryRun)
	if err != nil {
		return fmt.Errorf("loading config: %w", err)
	}

	// Export context type and maturity tier for pipeline stages.
	os.Setenv("SLOSCOPE_CONTEXT_TYPE", *contextType)
	os.Setenv("SLOSCOPE_MATURITY_TIER", *maturityTier)

	outDir := *out
	if outDir == "" {
		outDir = "."
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return fmt.Errorf("creating output directory: %w", err)
	}

	// ---- Step 2: Load and validate the baseline artifact ----
	schemasDir := drift.FindSchemasDir()
	fmt.Printf("Loading baseline from %s...\n", *baselinePath)

	baselineData, err := drift.LoadBaseline(*baselinePath, schemasDir)
	if err != nil {
		return fmt.Errorf("loading baseline: %w", err)
	}
	fmt.Println("Baseline loaded and validated successfully.")

	// ---- Step 3: Collect or load live evidence ----
	var liveEvidence json.RawMessage

	ctx := context.Background()
	windowDur, err := parseLookback(*window)
	if err != nil {
		return fmt.Errorf("parsing window: %w", err)
	}

	switch {
	case *evidencePath != "":
		// Load pre-collected evidence from file.
		liveEvidence, err = drift.LoadEvidenceFromFile(*evidencePath)
		if err != nil {
			return err
		}
		fmt.Printf("Loaded live evidence from %s\n", *evidencePath)

	case cfg.PromURL != "":
		// Collect live evidence from Prometheus.
		client := prom.NewClient(prom.ClientConfig{
			BaseURL: cfg.PromURL,
			Token:   cfg.PromToken,
		})

		fmt.Printf("Collecting live evidence from %s for %s/%s (window: %s)...\n",
			cfg.PromURL, *namespace, *service, *window)

		bundle, err := client.CollectEvidence(ctx, *service, *namespace, windowDur)
		if err != nil {
			return fmt.Errorf("collecting live evidence: %w", err)
		}

		// Enrich evidence with traces if TEMPO_URL is configured.
		if cfg.TempoURL != "" {
			fmt.Printf("Collecting trace evidence from %s...\n", cfg.TempoURL)
			traceClient := traces.NewClient(traces.ClientConfig{
				BaseURL: cfg.TempoURL,
				Token:   cfg.TempoToken,
			})
			traceData, err := traceClient.CollectTraceEvidence(ctx, *service, windowDur)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: trace collection failed: %v\n", err)
			} else {
				bundle.Series.Traces = traceData
				bundle.SchemaVersion = 2
				fmt.Println("Trace evidence collected")
			}
		}

		// Enrich evidence with logs if LOKI_URL is configured.
		if cfg.LokiURL != "" {
			fmt.Printf("Collecting log evidence from %s...\n", cfg.LokiURL)
			logClient := logs.NewClient(logs.ClientConfig{
				BaseURL: cfg.LokiURL,
				Token:   cfg.LokiToken,
			})
			logData, err := logClient.CollectLogEvidence(ctx, *service, *namespace, windowDur)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: log collection failed: %v\n", err)
			} else {
				bundle.Series.Logs = logData
				bundle.SchemaVersion = 2
				fmt.Println("Log evidence collected")
			}
		}

		liveEvidence, err = json.MarshalIndent(bundle, "", "  ")
		if err != nil {
			return fmt.Errorf("marshaling live evidence: %w", err)
		}
		fmt.Println("Live evidence collected successfully.")

	default:
		return fmt.Errorf("no evidence source: set PROM_URL or use --evidence to provide pre-collected evidence")
	}

	// Save live evidence artifact.
	evidenceFile := filepath.Join(outDir, "live-evidence.json")
	if err := os.WriteFile(evidenceFile, liveEvidence, 0o644); err != nil {
		return fmt.Errorf("writing live evidence: %w", err)
	}

	// ---- Step 4: Build the combined deviation input ----
	deviationInput, err := drift.BuildDeviationInput(liveEvidence, baselineData)
	if err != nil {
		return err
	}

	// Save the deviation input for auditability.
	deviationInputFile := filepath.Join(outDir, "deviation-input.json")
	if err := os.WriteFile(deviationInputFile, deviationInput, 0o644); err != nil {
		return fmt.Errorf("writing deviation input: %w", err)
	}

	// ---- Step 5: Run the deviation stage ----
	analysisDir, err := findAnalysisDir()
	if err != nil {
		return err
	}

	pipe := pipeline.New(pipeline.PipelineConfig{
		AnalysisDir: analysisDir,
	})

	fmt.Println("Running deviation analysis...")
	driftSignal, err := pipe.RunDeviation(ctx, deviationInput)
	if err != nil {
		// Expected to fail until deviation.py is implemented (M2).
		fmt.Fprintf(os.Stderr, "deviation stage not yet implemented: %v\n", err)
		fmt.Println("\nM1 complete: baseline loaded and validated, live evidence collected, deviation input assembled.")
		fmt.Printf("Artifacts saved to %s/:\n", outDir)
		fmt.Println("  - live-evidence.json")
		fmt.Println("  - deviation-input.json")
		return nil
	}

	// Save drift-signal artifact.
	driftSignalFile := filepath.Join(outDir, "drift-signal.json")
	if err := os.WriteFile(driftSignalFile, driftSignal, 0o644); err != nil {
		return fmt.Errorf("writing drift signal: %w", err)
	}
	fmt.Printf("Drift signal written to %s\n", driftSignalFile)

	// ---- Step 6: If dry-run, print and exit ----
	if *dryRun {
		fmt.Println("\n--- Drift Signal (dry-run) ---")
		fmt.Println(string(driftSignal))
		fmt.Println("\nDry-run complete. Skipping classification stage.")
		return nil
	}

	// ---- Step 7: Run the classification stage ----
	fmt.Println("Running classification analysis...")
	driftReport, err := pipe.RunClassification(ctx, driftSignal)
	if err != nil {
		fmt.Fprintf(os.Stderr, "classification stage not yet implemented: %v\n", err)
		return nil
	}

	// Save drift report (raw JSON).
	driftReportFile := filepath.Join(outDir, "drift-report.json")
	if err := os.WriteFile(driftReportFile, driftReport, 0o644); err != nil {
		return fmt.Errorf("writing drift report: %w", err)
	}
	fmt.Printf("Drift report written to %s\n", driftReportFile)

	// ---- Step 8: Render drift outputs ----

	// Render human-readable drift summary.
	fmt.Println("Rendering drift summary...")
	driftSummary, err := render.RenderDriftSummary(driftReport)
	if err != nil {
		return fmt.Errorf("rendering drift summary: %w", err)
	}
	summaryFile := filepath.Join(outDir, "drift-summary.txt")
	if err := os.WriteFile(summaryFile, []byte(driftSummary), 0o644); err != nil {
		return fmt.Errorf("writing drift summary: %w", err)
	}
	fmt.Printf("Drift summary written to %s\n", summaryFile)

	// Render drift audit bundle with 4 sections.
	fmt.Println("Rendering drift audit bundle...")
	auditSections := map[string]json.RawMessage{
		"baseline_reference": baselineData,
		"live_evidence":      liveEvidence,
		"drift_signals":      driftSignal,
		"drift_report":       driftReport,
	}
	auditBundle, err := render.RenderAuditBundle(*service, auditSections)
	if err != nil {
		return fmt.Errorf("rendering drift audit bundle: %w", err)
	}
	auditFile := filepath.Join(outDir, "drift-audit-bundle.json")
	if err := os.WriteFile(auditFile, auditBundle, 0o644); err != nil {
		return fmt.Errorf("writing drift audit bundle: %w", err)
	}
	fmt.Printf("Drift audit bundle written to %s\n", auditFile)

	// ---- Summary ----
	fmt.Printf("\nDrift analysis complete. Artifacts saved to %s/:\n", outDir)
	fmt.Println("  - live-evidence.json")
	fmt.Println("  - deviation-input.json")
	fmt.Println("  - drift-signal.json")
	fmt.Println("  - drift-report.json")
	fmt.Println("  - drift-summary.txt")
	fmt.Println("  - drift-audit-bundle.json")

	return nil
}
