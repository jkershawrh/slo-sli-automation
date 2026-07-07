// Package names centralizes validation and escaping for service identifiers.
package names

import (
	"fmt"
	"regexp"
	"strings"
)

var dnsLabelRE = regexp.MustCompile(`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`)

// ValidateKubernetesName validates a Kubernetes DNS label used for service and namespace names.
func ValidateKubernetesName(field, value string) error {
	if value == "" {
		return fmt.Errorf("%s is required", field)
	}
	if len(value) > 63 {
		return fmt.Errorf("%s %q is longer than 63 characters", field, value)
	}
	if !dnsLabelRE.MatchString(value) {
		return fmt.Errorf("%s %q must be a Kubernetes DNS label", field, value)
	}
	return nil
}

// PromLabelValue escapes a string for use inside a PromQL double-quoted label value.
func PromLabelValue(value string) string {
	replacer := strings.NewReplacer(
		`\`, `\\`,
		"\n", `\n`,
		`"`, `\"`,
	)
	return replacer.Replace(value)
}

// PromRegexLiteral returns a PromQL-safe regex that matches the literal value.
func PromRegexLiteral(value string) string {
	return PromLabelValue(regexp.QuoteMeta(value))
}
