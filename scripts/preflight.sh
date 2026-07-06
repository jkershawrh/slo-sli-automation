#!/usr/bin/env bash
set -euo pipefail

PASS=0
FAIL=0
WARN=0

check_pass() { echo "  [PASS] $1"; ((PASS++)) || true; }
check_fail() { echo "  [FAIL] $1"; ((FAIL++)) || true; }
check_warn() { echo "  [WARN] $1"; ((WARN++)) || true; }

echo "=== sloscope preflight checks ==="
echo ""

# Go
if command -v go &>/dev/null; then
    check_pass "Go installed: $(go version | awk '{print $3}')"
else
    check_fail "Go not found"
fi

# Python 3
if command -v python3 &>/dev/null; then
    check_pass "Python3 installed: $(python3 --version 2>&1)"
else
    check_fail "Python3 not found"
fi

# pytest
if python3 -m pytest --version &>/dev/null 2>&1; then
    check_pass "pytest available"
else
    check_fail "pytest not available (pip3 install pytest)"
fi

# jsonschema
if python3 -c "import jsonschema" 2>/dev/null; then
    check_pass "jsonschema package installed"
else
    check_fail "jsonschema not installed (pip3 install jsonschema)"
fi

# PROM_URL
if [ -n "${PROM_URL:-}" ]; then
    check_pass "PROM_URL set"
else
    check_warn "PROM_URL not set (required for live Prometheus queries, not for fixture mode)"
fi

# LLM_BASE_URL
if [ -n "${LLM_BASE_URL:-}" ]; then
    check_pass "LLM_BASE_URL set"
else
    check_warn "LLM_BASE_URL not set (required for full runs, not for --dry-run)"
fi

# promtool
if command -v promtool &>/dev/null; then
    check_pass "promtool available"
else
    check_warn "promtool not found (needed for Prometheus rule validation)"
fi

# Drift-specific checks
echo ""
echo "--- Drift-specific checks ---"

# Check that a sample baseline validates
if python3 -c "
import sys
sys.path.insert(0, 'analysis')
from schemas.validate import validate
import json
with open('testdata/drift_baseline_reference.json') as f:
    validate(json.load(f), 'baseline')
" 2>/dev/null; then
    check_pass "Sample baseline validates against schema"
else
    check_fail "Sample baseline does not validate"
fi

echo ""
echo "Results: $PASS passed, $FAIL failed, $WARN warnings"

if [ $FAIL -gt 0 ]; then
    echo "Preflight FAILED"
    exit 1
else
    echo "Preflight PASSED"
    exit 0
fi
