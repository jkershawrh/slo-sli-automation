package render

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
)

// AuditBundle is a tamper-evident container holding all SLO pipeline artifacts.
type AuditBundle struct {
	SchemaVersion int                    `json:"schema_version"`
	Service       string                 `json:"service"`
	Sections      map[string]AuditSection `json:"sections"`
	ContentHashes map[string]string      `json:"content_hashes"`
}

// AuditSection wraps a raw JSON artifact within the audit bundle.
type AuditSection struct {
	Data json.RawMessage `json:"data"`
}

// RenderAuditBundle creates an audit bundle with content hashes for each section.
func RenderAuditBundle(service string, sections map[string]json.RawMessage) (json.RawMessage, error) {
	bundle := AuditBundle{
		SchemaVersion: 1,
		Service:       service,
		Sections:      make(map[string]AuditSection),
		ContentHashes: make(map[string]string),
	}

	// Sort section names for deterministic output
	names := make([]string, 0, len(sections))
	for name := range sections {
		names = append(names, name)
	}
	sort.Strings(names)

	for _, name := range names {
		data := sections[name]
		// Compact the JSON before hashing so the hash is stable
		// across serialization round-trips (MarshalIndent reformats nested RawMessage).
		compacted, err := compactJSON(data)
		if err != nil {
			return nil, fmt.Errorf("compacting section %q: %w", name, err)
		}
		hash := sha256.Sum256(compacted)
		bundle.Sections[name] = AuditSection{Data: compacted}
		bundle.ContentHashes[name] = hex.EncodeToString(hash[:])
	}

	// Serialize with sorted keys for determinism
	result, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("marshaling audit bundle: %w", err)
	}

	return json.RawMessage(result), nil
}

// VerifyAuditBundle checks that all content hashes in the bundle are correct.
func VerifyAuditBundle(bundleJSON json.RawMessage) error {
	var bundle AuditBundle
	if err := json.Unmarshal(bundleJSON, &bundle); err != nil {
		return fmt.Errorf("parsing audit bundle: %w", err)
	}

	for name, section := range bundle.Sections {
		expectedHash, ok := bundle.ContentHashes[name]
		if !ok {
			return fmt.Errorf("missing content hash for section %q", name)
		}

		// Compact before hashing to match what RenderAuditBundle does
		compacted, err := compactJSON(section.Data)
		if err != nil {
			return fmt.Errorf("compacting section %q for verification: %w", name, err)
		}
		actualHash := sha256.Sum256(compacted)
		actualHashStr := hex.EncodeToString(actualHash[:])

		if actualHashStr != expectedHash {
			return fmt.Errorf("content hash mismatch for section %q: expected %s, got %s", name, expectedHash, actualHashStr)
		}
	}

	// Check that every hash has a corresponding section
	for name := range bundle.ContentHashes {
		if _, ok := bundle.Sections[name]; !ok {
			return fmt.Errorf("content hash exists for non-existent section %q", name)
		}
	}

	return nil
}

// compactJSON normalizes JSON bytes to their compact form so that hashes
// are stable regardless of whitespace or indentation differences.
func compactJSON(data json.RawMessage) ([]byte, error) {
	var buf bytes.Buffer
	if err := json.Compact(&buf, data); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}
