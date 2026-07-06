"""Schema validation utilities for SLO artifacts."""

import json
import os
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).parent


def load_schema(name):
    """Load a JSON schema by name (without .schema.json suffix)."""
    path = SCHEMA_DIR / "{}.schema.json".format(name)
    with open(path) as f:
        return json.load(f)


def validate(data, schema_name):
    """Validate data against a named schema. Raises jsonschema.ValidationError on failure."""
    schema = load_schema(schema_name)
    jsonschema.validate(instance=data, schema=schema)


def is_valid(data, schema_name):
    """Return True if data validates, False otherwise."""
    try:
        validate(data, schema_name)
        return True
    except jsonschema.ValidationError:
        return False
