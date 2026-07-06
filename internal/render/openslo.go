package render

import (
	"encoding/json"
	"fmt"
	"strings"
)

// Proposal represents an LLM-generated SLO proposal.
type Proposal struct {
	SchemaVersion        int    `json:"schema_version"`
	Service              string `json:"service"`
	BaselineSchemaVersion int   `json:"baseline_schema_version"`
	MaturityTier         string `json:"maturity_tier,omitempty"`
	SLOs                 []SLO  `json:"slos"`
}

// SLO represents a single Service Level Objective within a proposal.
type SLO struct {
	SLIName        string         `json:"sli_name"`
	SLIType        string         `json:"sli_type"`
	SLIDefinition  string         `json:"sli_definition"`
	Target         float64        `json:"target"`
	TargetOp       string         `json:"target_op"`
	TargetUnit     string         `json:"target_unit"`
	ErrorBudgetPct float64        `json:"error_budget_percent"`
	Headroom       *Headroom      `json:"headroom,omitempty"`
	BurnRatePolicy BurnRatePolicy `json:"burn_rate_policy"`
	Rationale      string         `json:"rationale"`
	RequiresReview bool           `json:"requires_review"`
	ReviewReason   string         `json:"review_reason"`
}

// Headroom captures the observed margin between actual performance and the SLO target.
type Headroom struct {
	ObservedValue   float64 `json:"observed_value"`
	Margin          float64 `json:"margin"`
	MarginRationale string  `json:"margin_rationale"`
}

// BurnRatePolicy defines the multi-window multi-burn-rate alerting policy.
type BurnRatePolicy struct {
	Windows []BurnRateWindow `json:"windows"`
}

// BurnRateWindow is a single burn rate alerting window with long/short lookback.
type BurnRateWindow struct {
	LongWindow  string  `json:"long_window"`
	ShortWindow string  `json:"short_window"`
	BurnRate    float64 `json:"burn_rate"`
	Severity    string  `json:"severity"`
}

// RenderOpenSLO generates OpenSLO YAML from a proposal.
func RenderOpenSLO(proposalJSON json.RawMessage) (string, error) {
	var proposal Proposal
	if err := json.Unmarshal(proposalJSON, &proposal); err != nil {
		return "", fmt.Errorf("parsing proposal: %w", err)
	}

	var sb strings.Builder

	// Generate one SLO document per proposed SLO
	for i, slo := range proposal.SLOs {
		if i > 0 {
			sb.WriteString("---\n")
		}

		// Sanitize the SLI name for use as a Kubernetes-style identifier
		name := sanitizeName(slo.SLIName)

		sb.WriteString("apiVersion: openslo/v1\n")
		sb.WriteString("kind: SLO\n")
		sb.WriteString("metadata:\n")
		sb.WriteString(fmt.Sprintf("  name: %s-%s\n", sanitizeName(proposal.Service), name))
		sb.WriteString(fmt.Sprintf("  displayName: %s\n", slo.SLIName))
		sb.WriteString("spec:\n")
		sb.WriteString(fmt.Sprintf("  service: %s\n", proposal.Service))
		sb.WriteString(fmt.Sprintf("  description: %s\n", slo.SLIDefinition))
		sb.WriteString("  budgetingMethod: Occurrences\n")
		sb.WriteString("  objectives:\n")
		sb.WriteString(fmt.Sprintf("    - displayName: %s\n", slo.SLIName))

		// For latency SLOs, target is a ratio derived from the error budget,
		// and we include the threshold value with an operator.
		// For non-latency SLOs, target is the value directly with an optional operator.
		if slo.SLIType == "latency" {
			// Latency SLOs: target is the ratio from error budget, value is the threshold
			sb.WriteString(fmt.Sprintf("      target: %g\n", (100.0-slo.ErrorBudgetPct)/100.0))
			sb.WriteString(fmt.Sprintf("      op: %s\n", slo.TargetOp))
			sb.WriteString(fmt.Sprintf("      value: %g\n", slo.Target))
		} else {
			// Non-latency SLOs: target is the value directly
			sb.WriteString(fmt.Sprintf("      target: %g\n", slo.Target))
			if slo.TargetOp != "" {
				sb.WriteString(fmt.Sprintf("      op: %s\n", slo.TargetOp))
			}
		}

		sb.WriteString("  indicator:\n")
		sb.WriteString("    metadata:\n")
		sb.WriteString(fmt.Sprintf("      name: %s-sli\n", name))
		sb.WriteString("    spec:\n")
		sb.WriteString("      ratioMetric:\n")
		sb.WriteString("        good:\n")
		sb.WriteString("          source: prometheus\n")
		sb.WriteString("        total:\n")
		sb.WriteString("          source: prometheus\n")

		// Alert policies from burn rate windows
		if len(slo.BurnRatePolicy.Windows) > 0 {
			sb.WriteString("  alertPolicies:\n")
			for _, w := range slo.BurnRatePolicy.Windows {
				sb.WriteString("    - kind: AlertPolicy\n")
				sb.WriteString("      metadata:\n")
				sb.WriteString(fmt.Sprintf("        name: %s-%s-%s\n", sanitizeName(proposal.Service), name, w.Severity))
				sb.WriteString("      spec:\n")
				sb.WriteString(fmt.Sprintf("        description: %s burn rate alert for %s\n", w.Severity, slo.SLIName))
				sb.WriteString(fmt.Sprintf("        severity: %s\n", w.Severity))
				sb.WriteString("        conditions:\n")
				sb.WriteString("          - kind: AlertCondition\n")
				sb.WriteString("            spec:\n")
				sb.WriteString("              condition:\n")
				sb.WriteString("                kind: Burnrate\n")
				sb.WriteString("                op: gt\n")
				sb.WriteString(fmt.Sprintf("                threshold: %g\n", w.BurnRate))
				sb.WriteString(fmt.Sprintf("                lookbackWindow: %s\n", w.LongWindow))
				sb.WriteString(fmt.Sprintf("                alertAfter: %s\n", w.ShortWindow))
			}
		}
	}

	return sb.String(), nil
}

// sanitizeName converts a human-readable name into a Kubernetes-style identifier
// containing only lowercase letters, digits, and hyphens.
func sanitizeName(s string) string {
	s = strings.ToLower(s)
	s = strings.ReplaceAll(s, " ", "-")
	s = strings.ReplaceAll(s, "_", "-")
	// Remove any characters that aren't alphanumeric or hyphens
	var result strings.Builder
	for _, c := range s {
		if (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' {
			result.WriteRune(c)
		}
	}
	return result.String()
}
