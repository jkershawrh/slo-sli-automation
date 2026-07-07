package config

import (
	"fmt"
	"strings"
	"testing"
)

func TestLoadAllVarsSet(t *testing.T) {
	t.Setenv("PROM_URL", "http://prometheus:9090")
	t.Setenv("PROM_TOKEN", "prom-secret-token")
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "llm-secret-key")
	t.Setenv("LLM_MODEL", "gpt-4")

	cfg, err := Load(false)
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
	if cfg.PromURL != "http://prometheus:9090" {
		t.Errorf("PromURL = %q, want %q", cfg.PromURL, "http://prometheus:9090")
	}
	if cfg.PromToken != "prom-secret-token" {
		t.Errorf("PromToken not set correctly")
	}
	if cfg.LLMBaseURL != "http://llm:8080" {
		t.Errorf("LLMBaseURL = %q, want %q", cfg.LLMBaseURL, "http://llm:8080")
	}
	if cfg.LLMAPIKey != "llm-secret-key" {
		t.Errorf("LLMAPIKey not set correctly")
	}
	if cfg.LLMModel != "gpt-4" {
		t.Errorf("LLMModel = %q, want %q", cfg.LLMModel, "gpt-4")
	}
}

func TestLoadTempoAndLokiFromEnv(t *testing.T) {
	// Tempo and Loki vars are always optional.
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "key")
	t.Setenv("LLM_MODEL", "model")
	t.Setenv("TEMPO_URL", "http://tempo:3200")
	t.Setenv("TEMPO_TOKEN", "tempo-token")
	t.Setenv("LOKI_URL", "http://loki:3100")
	t.Setenv("LOKI_TOKEN", "loki-token")

	cfg, err := Load(false)
	if err != nil {
		t.Fatalf("expected no error, got: %v", err)
	}
	if cfg.TempoURL != "http://tempo:3200" {
		t.Errorf("TempoURL = %q, want %q", cfg.TempoURL, "http://tempo:3200")
	}
	if cfg.TempoToken != "tempo-token" {
		t.Errorf("TempoToken not set correctly")
	}
	if cfg.LokiURL != "http://loki:3100" {
		t.Errorf("LokiURL = %q, want %q", cfg.LokiURL, "http://loki:3100")
	}
	if cfg.LokiToken != "loki-token" {
		t.Errorf("LokiToken not set correctly")
	}

	// Verify String() includes Tempo and Loki URLs but redacts tokens.
	str := cfg.String()
	if !strings.Contains(str, "http://tempo:3200") {
		t.Error("String() should include TEMPO_URL")
	}
	if !strings.Contains(str, "http://loki:3100") {
		t.Error("String() should include LOKI_URL")
	}
	if strings.Contains(str, "tempo-token") {
		t.Error("String() should redact TEMPO_TOKEN")
	}
	if strings.Contains(str, "loki-token") {
		t.Error("String() should redact LOKI_TOKEN")
	}
}

func TestLoadTempoAndLokiOptional(t *testing.T) {
	// Loading without Tempo/Loki vars should succeed.
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "key")
	t.Setenv("LLM_MODEL", "model")

	cfg, err := Load(false)
	if err != nil {
		t.Fatalf("expected no error without Tempo/Loki vars, got: %v", err)
	}
	if cfg.TempoURL != "" {
		t.Errorf("TempoURL = %q, want empty", cfg.TempoURL)
	}
	if cfg.LokiURL != "" {
		t.Errorf("LokiURL = %q, want empty", cfg.LokiURL)
	}
}

func TestLoadMissingPromURLSucceeds(t *testing.T) {
	// PROM_URL is not required at load time; the caller decides if it's needed.
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "llm-secret-key")
	t.Setenv("LLM_MODEL", "gpt-4")

	cfg, err := Load(false)
	if err != nil {
		t.Fatalf("expected no error when PROM_URL is missing, got: %v", err)
	}
	if cfg.PromURL != "" {
		t.Errorf("PromURL = %q, want empty string", cfg.PromURL)
	}
}

func TestLoadDryRunNoLLMVars(t *testing.T) {
	// In dry-run mode, LLM vars are not required.
	cfg, err := Load(true)
	if err != nil {
		t.Fatalf("expected no error in dry-run mode without LLM vars, got: %v", err)
	}
	if cfg.LLMBaseURL != "" {
		t.Errorf("LLMBaseURL = %q, want empty string", cfg.LLMBaseURL)
	}
	if cfg.LLMAPIKey != "" {
		t.Errorf("LLMAPIKey = %q, want empty string", cfg.LLMAPIKey)
	}
	if cfg.LLMModel != "" {
		t.Errorf("LLMModel = %q, want empty string", cfg.LLMModel)
	}
}

func TestLoadNonDryRunMissingLLMVarsFails(t *testing.T) {
	// Non-dry-run requires all LLM vars.
	tests := []struct {
		name    string
		setVars map[string]string
		wantErr string
	}{
		{
			name: "missing all LLM vars",
			setVars: map[string]string{},
			wantErr: "LLM_BASE_URL",
		},
		{
			name: "missing LLM_API_KEY",
			setVars: map[string]string{
				"LLM_BASE_URL": "http://llm:8080",
				"LLM_MODEL":    "gpt-4",
			},
			wantErr: "LLM_API_KEY",
		},
		{
			name: "missing LLM_MODEL",
			setVars: map[string]string{
				"LLM_BASE_URL": "http://llm:8080",
				"LLM_API_KEY":  "secret",
			},
			wantErr: "LLM_MODEL",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			for k, v := range tc.setVars {
				t.Setenv(k, v)
			}
			_, err := Load(false)
			if err == nil {
				t.Fatal("expected an error, got nil")
			}
			if !strings.Contains(err.Error(), tc.wantErr) {
				t.Errorf("error %q should mention %q", err.Error(), tc.wantErr)
			}
		})
	}
}

func TestSecretsNotExposed(t *testing.T) {
	t.Setenv("PROM_URL", "http://prometheus:9090")
	t.Setenv("PROM_TOKEN", "super-secret-prom-token")
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "super-secret-llm-key")
	t.Setenv("LLM_MODEL", "gpt-4")

	cfg, err := Load(false)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	str := cfg.String()
	if strings.Contains(str, "super-secret-prom-token") {
		t.Error("String() exposes PROM_TOKEN secret")
	}
	if strings.Contains(str, "super-secret-llm-key") {
		t.Error("String() exposes LLM_API_KEY secret")
	}
}

func TestSecretsNotInErrors(t *testing.T) {
	// Set an invalid PROM_URL along with secrets to verify errors don't leak them.
	t.Setenv("PROM_URL", "not-a-valid-url")
	t.Setenv("PROM_TOKEN", "super-secret-prom-token")
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "super-secret-llm-key")
	t.Setenv("LLM_MODEL", "gpt-4")

	_, err := Load(false)
	if err == nil {
		t.Fatal("expected error for invalid PROM_URL")
	}
	errMsg := fmt.Sprintf("%v", err)
	if strings.Contains(errMsg, "super-secret-prom-token") {
		t.Error("error message exposes PROM_TOKEN secret")
	}
	if strings.Contains(errMsg, "super-secret-llm-key") {
		t.Error("error message exposes LLM_API_KEY secret")
	}
}

func TestLoadInvalidPromURL(t *testing.T) {
	t.Setenv("PROM_URL", "not-a-valid-url")
	t.Setenv("LLM_BASE_URL", "http://llm:8080")
	t.Setenv("LLM_API_KEY", "key")
	t.Setenv("LLM_MODEL", "model")

	_, err := Load(false)
	if err == nil {
		t.Fatal("expected error for invalid PROM_URL, got nil")
	}
	if !strings.Contains(err.Error(), "PROM_URL") {
		t.Errorf("error %q should mention PROM_URL", err.Error())
	}
}
