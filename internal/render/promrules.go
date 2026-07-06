package render

import (
	"encoding/json"
	"fmt"
	"strings"
)

// RenderPrometheusRules generates Prometheus recording and alerting rules from a proposal.
func RenderPrometheusRules(proposalJSON json.RawMessage, service string) (string, error) {
	var proposal Proposal
	if err := json.Unmarshal(proposalJSON, &proposal); err != nil {
		return "", fmt.Errorf("parsing proposal: %w", err)
	}

	var sb strings.Builder
	sb.WriteString("groups:\n")

	// Recording rules group
	sb.WriteString(fmt.Sprintf("  - name: %s_slo_recording\n", sanitizeName(service)))
	sb.WriteString("    rules:\n")

	for _, slo := range proposal.SLOs {
		name := sanitizeName(slo.SLIName)

		switch slo.SLIType {
		case "availability", "error_rate":
			// Recording rule for error ratio
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:error_ratio\n", name))
			sb.WriteString("        expr: |\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{service=\"%s\",code=~\"5..\"}[5m]))\n", service))
			sb.WriteString("          /\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{service=\"%s\"}[5m]))\n", service))
			sb.WriteString("        labels:\n")
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))

		case "latency":
			// Recording rule for latency SLI
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:latency_ratio\n", name))
			sb.WriteString("        expr: |\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_request_duration_seconds_bucket{service=\"%s\",le=\"%g\"}[5m]))\n", service, slo.SLATarget/1000))
			sb.WriteString("          /\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_request_duration_seconds_count{service=\"%s\"}[5m]))\n", service))
			sb.WriteString("        labels:\n")
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))

		case "throughput":
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:throughput_rps\n", name))
			sb.WriteString(fmt.Sprintf("        expr: |\n"))
			sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{service=\"%s\"}[5m]))\n", service))
			sb.WriteString(fmt.Sprintf("        labels:\n"))
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))

		case "saturation":
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:cpu_utilization\n", name))
			sb.WriteString(fmt.Sprintf("        expr: |\n"))
			sb.WriteString(fmt.Sprintf("          avg(rate(container_cpu_usage_seconds_total{pod=~\"%s.*\"}[5m]))\n", service))
			sb.WriteString(fmt.Sprintf("        labels:\n"))
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))
		}
	}

	// Alerting rules group -- multi-window multi-burn-rate
	sb.WriteString(fmt.Sprintf("\n  - name: %s_slo_alerts\n", sanitizeName(service)))
	sb.WriteString("    rules:\n")

	for _, slo := range proposal.SLOs {
		name := sanitizeName(slo.SLIName)
		errorBudget := slo.ErrorBudgetPct / 100.0

		for _, w := range slo.BurnRatePolicy.Windows {
			alertName := fmt.Sprintf("SLO%sBurnRate%s",
				toPascalCase(slo.SLIName),
				capitalize(w.Severity))

			sb.WriteString(fmt.Sprintf("      - alert: %s\n", alertName))
			sb.WriteString("        expr: |\n")

			switch slo.SLIType {
			case "latency":
				sb.WriteString("          (\n")
				sb.WriteString(fmt.Sprintf("            1 - (sum(rate(http_request_duration_seconds_bucket{service=\"%s\",le=\"%g\"}[%s])) / sum(rate(http_request_duration_seconds_count{service=\"%s\"}[%s])))\n",
					service, slo.SLATarget/1000, w.LongWindow, service, w.LongWindow))
				sb.WriteString(fmt.Sprintf("          ) > %g * %g\n", w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString("          (\n")
				sb.WriteString(fmt.Sprintf("            1 - (sum(rate(http_request_duration_seconds_bucket{service=\"%s\",le=\"%g\"}[%s])) / sum(rate(http_request_duration_seconds_count{service=\"%s\"}[%s])))\n",
					service, slo.SLATarget/1000, w.ShortWindow, service, w.ShortWindow))
				sb.WriteString(fmt.Sprintf("          ) > %g * %g\n", w.BurnRate, errorBudget))

			case "availability", "error_rate":
				sb.WriteString(fmt.Sprintf("          slo:%s:error_ratio{service=\"%s\"}[%s] > %g * %g\n",
					name, service, w.LongWindow, w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString(fmt.Sprintf("          slo:%s:error_ratio{service=\"%s\"}[%s] > %g * %g\n",
					name, service, w.ShortWindow, w.BurnRate, errorBudget))

			case "throughput":
				// Alert when throughput drops below target * (1 - burn_rate * error_budget)
				sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{service=\"%s\"}[%s])) < %g * (1 - %g * %g)\n",
					service, w.LongWindow, slo.SLATarget, w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{service=\"%s\"}[%s])) < %g * (1 - %g * %g)\n",
					service, w.ShortWindow, slo.SLATarget, w.BurnRate, errorBudget))

			case "saturation":
				// Alert when CPU utilization exceeds target + burn_rate * error_budget
				sb.WriteString(fmt.Sprintf("          avg(rate(container_cpu_usage_seconds_total{pod=~\"%s.*\"}[%s])) > %g + %g * %g\n",
					service, w.LongWindow, slo.SLATarget, w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString(fmt.Sprintf("          avg(rate(container_cpu_usage_seconds_total{pod=~\"%s.*\"}[%s])) > %g + %g * %g\n",
					service, w.ShortWindow, slo.SLATarget, w.BurnRate, errorBudget))
			}

			sb.WriteString("        labels:\n")
			sb.WriteString(fmt.Sprintf("          severity: %s\n", w.Severity))
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))
			sb.WriteString("        annotations:\n")
			sb.WriteString(fmt.Sprintf("          summary: %s burn rate is %.1fx the error budget\n", slo.SLIName, w.BurnRate))
			sb.WriteString("          description: >-\n")
			sb.WriteString(fmt.Sprintf("            The %s SLO for %s is burning through its error budget\n", slo.SLIName, service))
			sb.WriteString(fmt.Sprintf("            at %.1fx the sustainable rate over the %s window.\n", w.BurnRate, w.LongWindow))
		}
	}

	return sb.String(), nil
}

// toPascalCase converts a snake_case or space-separated string to PascalCase.
func toPascalCase(s string) string {
	s = strings.ReplaceAll(s, "_", " ")
	words := strings.Fields(s)
	for i, word := range words {
		if len(word) > 0 {
			words[i] = strings.ToUpper(word[:1]) + word[1:]
		}
	}
	return strings.Join(words, "")
}

// capitalize uppercases the first letter of a string.
func capitalize(s string) string {
	if len(s) == 0 {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
