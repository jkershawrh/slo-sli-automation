// Package schema validates Go structs against the project's JSON schemas.
package schema

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// Validator loads JSON schemas from an fs.FS and validates Go structs.
type Validator struct {
	schemas fs.FS
}

// NewValidator creates a Validator that reads schemas from the given filesystem.
func NewValidator(schemas fs.FS) *Validator {
	return &Validator{schemas: schemas}
}

// NewValidatorFromDir creates a Validator that reads schemas from a directory on disk.
func NewValidatorFromDir(dir string) *Validator {
	return &Validator{schemas: os.DirFS(dir)}
}

// Validate marshals data to JSON and validates it against the named schema.
// schemaName should be the filename, e.g. "evidence.schema.json".
func (v *Validator) Validate(data interface{}, schemaName string) error {
	// Marshal the Go struct to JSON.
	jsonBytes, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("marshaling data: %w", err)
	}

	// Unmarshal into a generic interface{} for the validator.
	var doc interface{}
	if err := json.Unmarshal(jsonBytes, &doc); err != nil {
		return fmt.Errorf("unmarshaling JSON for validation: %w", err)
	}

	// Load the schema from the filesystem.
	schemaBytes, err := fs.ReadFile(v.schemas, schemaName)
	if err != nil {
		return fmt.Errorf("loading schema %s: %w", schemaName, err)
	}

	// Unmarshal the schema itself.
	var schemaDoc interface{}
	if err := json.Unmarshal(schemaBytes, &schemaDoc); err != nil {
		return fmt.Errorf("unmarshaling schema %s: %w", schemaName, err)
	}

	// Compile the schema.
	compiler := jsonschema.NewCompiler()
	if err := compiler.AddResource(schemaName, schemaDoc); err != nil {
		return fmt.Errorf("adding schema resource: %w", err)
	}

	sch, err := compiler.Compile(schemaName)
	if err != nil {
		return fmt.Errorf("compiling schema %s: %w", schemaName, err)
	}

	// Validate the document.
	if err := sch.Validate(doc); err != nil {
		return &ValidationError{
			SchemaName: schemaName,
			Err:        err,
		}
	}

	return nil
}

// ValidationError wraps a schema validation failure with context.
type ValidationError struct {
	SchemaName string
	Err        error
}

func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation against %s failed: %s", e.SchemaName, summarizeErrors(e.Err))
}

func (e *ValidationError) Unwrap() error {
	return e.Err
}

func summarizeErrors(err error) string {
	if err == nil {
		return ""
	}
	msg := err.Error()
	// Truncate very long validation error messages.
	if len(msg) > 500 {
		lines := strings.SplitN(msg, "\n", 10)
		if len(lines) > 5 {
			return strings.Join(lines[:5], "\n") + "\n... (truncated)"
		}
	}
	return msg
}
