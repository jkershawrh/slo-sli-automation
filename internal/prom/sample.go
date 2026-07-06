package prom

import (
	"encoding/json"
	"fmt"
	"strconv"
)

// UnmarshalJSON decodes a Prometheus sample pair from the wire format
// [unix_timestamp, "string_value"].
func (sp *SamplePair) UnmarshalJSON(data []byte) error {
	var raw [2]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return fmt.Errorf("sample pair: expected 2-element array: %w", err)
	}

	if err := json.Unmarshal(raw[0], &sp.Timestamp); err != nil {
		return fmt.Errorf("sample pair timestamp: %w", err)
	}

	var valStr string
	if err := json.Unmarshal(raw[1], &valStr); err != nil {
		return fmt.Errorf("sample pair value: %w", err)
	}

	v, err := strconv.ParseFloat(valStr, 64)
	if err != nil {
		return fmt.Errorf("sample pair value %q: %w", valStr, err)
	}
	sp.Value = v
	return nil
}

// MarshalJSON encodes a SamplePair back to the Prometheus wire format.
func (sp SamplePair) MarshalJSON() ([]byte, error) {
	return json.Marshal([2]interface{}{sp.Timestamp, strconv.FormatFloat(sp.Value, 'f', -1, 64)})
}
