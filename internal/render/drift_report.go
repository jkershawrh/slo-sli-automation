package render

import (
	"encoding/json"
	"fmt"
	"strings"
)

// DriftReport represents the LLM classification output for a drift analysis.
type DriftReport struct {
	SchemaVersion   int              `json:"schema_version"`
	Service         string           `json:"service"`
	Classification  string           `json:"classification"`
	Severity        string           `json:"severity"`
	LikelyCause     string           `json:"likely_cause"`
	Recommendations []Recommendation `json:"recommendations"`
}

// Recommendation is a single remediation recommendation from the LLM.
type Recommendation struct {
	Action     string `json:"action"`
	Confidence string `json:"confidence"`
	Rationale  string `json:"rationale"`
}

// RenderDriftSummary takes a drift-report JSON (LLM output) and produces a
// human-readable text summary suitable for terminal display or file output.
func RenderDriftSummary(reportJSON json.RawMessage) (string, error) {
	var report DriftReport
	if err := json.Unmarshal(reportJSON, &report); err != nil {
		return "", fmt.Errorf("parsing drift report: %w", err)
	}

	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("DRIFT REPORT: %s\n", report.Service))
	sb.WriteString(strings.Repeat("=", 60) + "\n\n")
	sb.WriteString(fmt.Sprintf("Classification: %s\n", strings.ReplaceAll(report.Classification, "_", " ")))
	sb.WriteString(fmt.Sprintf("Severity:       %s\n", strings.ToUpper(report.Severity)))
	sb.WriteString(fmt.Sprintf("\nLikely Cause:\n  %s\n", report.LikelyCause))
	sb.WriteString("\nRecommendations:\n")

	for i, rec := range report.Recommendations {
		sb.WriteString(fmt.Sprintf("\n  %d. [%s confidence] %s\n", i+1, rec.Confidence, rec.Action))
		sb.WriteString(fmt.Sprintf("     Rationale: %s\n", rec.Rationale))
	}

	sb.WriteString(fmt.Sprintf("\n%s\n", strings.Repeat("-", 60)))
	sb.WriteString("NOTE: These are recommendations for human review, not automated actions.\n")

	return sb.String(), nil
}
