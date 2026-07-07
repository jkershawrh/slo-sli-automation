package render

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/sloscope/sloscope/internal/names"
)

// RenderPrometheusRules generates Prometheus recording and alerting rules from a proposal.
func RenderPrometheusRules(proposalJSON json.RawMessage, service, namespace string) (string, error) {
	var proposal Proposal
	if err := json.Unmarshal(proposalJSON, &proposal); err != nil {
		return "", fmt.Errorf("parsing proposal: %w", err)
	}
	if namespace == "" {
		namespace = "default"
	}
	if err := names.ValidateKubernetesName("service", service); err != nil {
		return "", err
	}
	if err := names.ValidateKubernetesName("namespace", namespace); err != nil {
		return "", err
	}

	serviceLabel := names.PromLabelValue(service)
	namespaceLabel := names.PromLabelValue(namespace)
	servicePodRegex := names.PromRegexLiteral(service)
	selector := fmt.Sprintf(`service="%s",namespace="%s"`, serviceLabel, namespaceLabel)
	labelSelector := fmt.Sprintf(`{service="%s",namespace="%s"}`, serviceLabel, namespaceLabel)

	var sb strings.Builder
	sb.WriteString("groups:\n")

	// Recording rules group
	sb.WriteString(fmt.Sprintf("  - name: %s_slo_recording\n", sanitizeMetricNameSegment(service)))
	sb.WriteString("    rules:\n")

	for _, slo := range proposal.SLOs {
		name := sanitizeMetricNameSegment(slo.SLIName)

		switch slo.SLIType {
		case "availability", "error_rate":
			// Recording rule for error ratio
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:error_ratio\n", name))
			sb.WriteString("        expr: |\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{%s,code=~\"5..\"}[5m]))\n", selector))
			sb.WriteString("          /\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{%s}[5m]))\n", selector))
			sb.WriteString("        labels:\n")
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          namespace: %s\n", namespace))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))

		case "latency":
			// Recording rule for latency SLI
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:latency_ratio\n", name))
			sb.WriteString("        expr: |\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_request_duration_seconds_bucket{%s,le=\"%g\"}[5m]))\n", selector, slo.SLATarget/1000))
			sb.WriteString("          /\n")
			sb.WriteString(fmt.Sprintf("          sum(rate(http_request_duration_seconds_count{%s}[5m]))\n", selector))
			sb.WriteString("        labels:\n")
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          namespace: %s\n", namespace))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))

		case "throughput":
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:throughput_rps\n", name))
			sb.WriteString(fmt.Sprintf("        expr: |\n"))
			sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{%s}[5m]))\n", selector))
			sb.WriteString(fmt.Sprintf("        labels:\n"))
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          namespace: %s\n", namespace))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))

		case "saturation":
			sb.WriteString(fmt.Sprintf("      - record: slo:%s:cpu_utilization\n", name))
			sb.WriteString(fmt.Sprintf("        expr: |\n"))
			sb.WriteString(fmt.Sprintf("          avg(rate(container_cpu_usage_seconds_total{namespace=\"%s\",pod=~\"%s.*\"}[5m]))\n", namespaceLabel, servicePodRegex))
			sb.WriteString(fmt.Sprintf("        labels:\n"))
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          namespace: %s\n", namespace))
			sb.WriteString(fmt.Sprintf("          slo: %s\n", name))
		}
	}

	// Alerting rules group -- multi-window multi-burn-rate
	sb.WriteString(fmt.Sprintf("\n  - name: %s_slo_alerts\n", sanitizeMetricNameSegment(service)))
	sb.WriteString("    rules:\n")

	for _, slo := range proposal.SLOs {
		name := sanitizeMetricNameSegment(slo.SLIName)
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
				sb.WriteString(fmt.Sprintf("            1 - (sum(rate(http_request_duration_seconds_bucket{%s,le=\"%g\"}[%s])) / sum(rate(http_request_duration_seconds_count{%s}[%s])))\n",
					selector, slo.SLATarget/1000, w.LongWindow, selector, w.LongWindow))
				sb.WriteString(fmt.Sprintf("          ) > %g * %g\n", w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString("          (\n")
				sb.WriteString(fmt.Sprintf("            1 - (sum(rate(http_request_duration_seconds_bucket{%s,le=\"%g\"}[%s])) / sum(rate(http_request_duration_seconds_count{%s}[%s])))\n",
					selector, slo.SLATarget/1000, w.ShortWindow, selector, w.ShortWindow))
				sb.WriteString(fmt.Sprintf("          ) > %g * %g\n", w.BurnRate, errorBudget))

			case "availability", "error_rate":
				sb.WriteString(fmt.Sprintf("          avg_over_time(slo:%s:error_ratio%s[%s]) > %g * %g\n",
					name, labelSelector, w.LongWindow, w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString(fmt.Sprintf("          avg_over_time(slo:%s:error_ratio%s[%s]) > %g * %g\n",
					name, labelSelector, w.ShortWindow, w.BurnRate, errorBudget))

			case "throughput":
				// Alert when throughput drops below target * (1 - burn_rate * error_budget)
				sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{%s}[%s])) < %g * (1 - %g * %g)\n",
					selector, w.LongWindow, slo.SLATarget, w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString(fmt.Sprintf("          sum(rate(http_requests_total{%s}[%s])) < %g * (1 - %g * %g)\n",
					selector, w.ShortWindow, slo.SLATarget, w.BurnRate, errorBudget))

			case "saturation":
				// Alert when CPU utilization exceeds target + burn_rate * error_budget
				sb.WriteString(fmt.Sprintf("          avg(rate(container_cpu_usage_seconds_total{namespace=\"%s\",pod=~\"%s.*\"}[%s])) > %g + %g * %g\n",
					namespaceLabel, servicePodRegex, w.LongWindow, slo.SLATarget, w.BurnRate, errorBudget))
				sb.WriteString("          and\n")
				sb.WriteString(fmt.Sprintf("          avg(rate(container_cpu_usage_seconds_total{namespace=\"%s\",pod=~\"%s.*\"}[%s])) > %g + %g * %g\n",
					namespaceLabel, servicePodRegex, w.ShortWindow, slo.SLATarget, w.BurnRate, errorBudget))
			}

			sb.WriteString("        labels:\n")
			sb.WriteString(fmt.Sprintf("          severity: %s\n", w.Severity))
			sb.WriteString(fmt.Sprintf("          service: %s\n", service))
			sb.WriteString(fmt.Sprintf("          namespace: %s\n", namespace))
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

var invalidMetricChars = regexp.MustCompile(`[^a-zA-Z0-9_]`)
var repeatedUnderscores = regexp.MustCompile(`_+`)

func sanitizeMetricNameSegment(s string) string {
	s = strings.ToLower(s)
	s = strings.ReplaceAll(s, "-", "_")
	s = strings.ReplaceAll(s, " ", "_")
	s = invalidMetricChars.ReplaceAllString(s, "_")
	s = repeatedUnderscores.ReplaceAllString(s, "_")
	s = strings.Trim(s, "_")
	if s == "" {
		return "unnamed"
	}
	if s[0] >= '0' && s[0] <= '9' {
		return "_" + s
	}
	return s
}

// toPascalCase converts a snake_case or space-separated string to PascalCase.
func toPascalCase(s string) string {
	s = strings.ReplaceAll(s, "_", " ")
	s = strings.ReplaceAll(s, "-", " ")
	words := strings.Fields(s)
	var cleanedWords []string
	for _, word := range words {
		cleaned := invalidMetricChars.ReplaceAllString(word, "")
		if len(cleaned) > 0 {
			cleanedWords = append(cleanedWords, strings.ToUpper(cleaned[:1])+cleaned[1:])
		}
	}
	if len(cleanedWords) == 0 {
		return "Unnamed"
	}
	return strings.Join(cleanedWords, "")
}

// capitalize uppercases the first letter of a string.
func capitalize(s string) string {
	if len(s) == 0 {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
