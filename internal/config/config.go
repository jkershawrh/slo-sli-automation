// Package config resolves sloscope configuration from environment variables.
package config

import (
	"fmt"
	"net/url"
	"os"
	"strings"
)

// Config holds the resolved configuration for sloscope.
type Config struct {
	PromURL    string
	PromToken  string
	LLMBaseURL string
	LLMAPIKey  string
	LLMModel   string
}

// Load reads configuration from environment variables.
// When dryRun is true, LLM configuration (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)
// is not required. PROM_URL is validated if present but never required by Load —
// the caller decides whether it is needed.
func Load(dryRun bool) (*Config, error) {
	cfg := &Config{
		PromURL:    os.Getenv("PROM_URL"),
		PromToken:  os.Getenv("PROM_TOKEN"),
		LLMBaseURL: os.Getenv("LLM_BASE_URL"),
		LLMAPIKey:  os.Getenv("LLM_API_KEY"),
		LLMModel:   os.Getenv("LLM_MODEL"),
	}

	// Validate PROM_URL if set.
	if cfg.PromURL != "" {
		u, err := url.ParseRequestURI(cfg.PromURL)
		if err != nil || u.Scheme == "" || u.Host == "" {
			return nil, fmt.Errorf("PROM_URL is not a valid URL")
		}
	}

	// In non-dry-run mode, all LLM vars are required.
	if !dryRun {
		var missing []string
		if cfg.LLMBaseURL == "" {
			missing = append(missing, "LLM_BASE_URL")
		}
		if cfg.LLMAPIKey == "" {
			missing = append(missing, "LLM_API_KEY")
		}
		if cfg.LLMModel == "" {
			missing = append(missing, "LLM_MODEL")
		}
		if len(missing) > 0 {
			return nil, fmt.Errorf("required environment variables not set: %s", strings.Join(missing, ", "))
		}
	}

	return cfg, nil
}

// String returns a human-readable representation of the config.
// Secrets (PROM_TOKEN, LLM_API_KEY) are redacted.
func (c *Config) String() string {
	promToken := "<not set>"
	if c.PromToken != "" {
		promToken = "<redacted>"
	}
	apiKey := "<not set>"
	if c.LLMAPIKey != "" {
		apiKey = "<redacted>"
	}
	return fmt.Sprintf(
		"PROM_URL=%s, PROM_TOKEN=%s, LLM_BASE_URL=%s, LLM_API_KEY=%s, LLM_MODEL=%s",
		c.PromURL, promToken, c.LLMBaseURL, apiKey, c.LLMModel,
	)
}
