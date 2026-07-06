"""Canonical JSON serializer for deterministic, byte-for-byte reproducible output."""

import json
import math


def _format_float(value):
    """Format a float to 6 significant digits with no trailing zeros."""
    if value == 0:
        return 0.0
    if math.isnan(value) or math.isinf(value):
        raise ValueError("Cannot serialize {}".format(value))
    # Use 6 significant digits
    formatted = float("{:.6g}".format(value))
    return formatted


def _clean_for_json(obj):
    """Recursively format all floats in a nested structure."""
    if isinstance(obj, float):
        return _format_float(obj)
    elif isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_for_json(item) for item in obj]
    return obj


def serialize(data):
    """Serialize to canonical JSON: sorted keys, 2-space indent, formatted floats."""
    cleaned = _clean_for_json(data)
    return json.dumps(cleaned, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
