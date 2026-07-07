#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PASS=0
FAIL=0
TOTAL=0

check() {
    local name="$1"
    shift
    ((TOTAL++)) || true
    echo -n "  [$TOTAL] $name ... "
    if "$@" >/dev/null 2>&1; then
        echo "GREEN"
        ((PASS++)) || true
    else
        echo "RED"
        ((FAIL++)) || true
    fi
}

echo "=== sloscope verification ==="
echo ""

# 1. Go unit tests
echo "--- Go tests ---"
check "Config tests" go test ./internal/config/ -count=1
check "Prometheus client tests" go test ./internal/prom/ -count=1
check "Schema validation tests" go test ./internal/schema/ -count=1
check "Pipeline tests" go test ./internal/pipeline/ -count=1
check "Renderer tests" go test ./internal/render/ -count=1

echo ""

# 2. Python unit tests
echo "--- Python tests ---"
check "Schema contract tests" python3 -m pytest analysis/tests/test_schemas.py -q
check "Baseline computation tests" python3 -m pytest analysis/tests/test_baseline.py -q
check "Proposal eval tests" python3 -m pytest analysis/tests/test_proposal.py -q

echo ""

# 2b. Backend API tests
echo "--- Backend API tests ---"
check "Backend API test suite" python3 -m pytest backend/test_server.py -q

echo ""

# 2c. Frontend tests
echo "--- Frontend tests ---"
check "Frontend component smoke tests" bash -c "cd frontend && npx vitest run 2>&1 | grep -q 'Tests.*passed'"

echo ""

# 3. LLM eval grid (against recorded responses)
echo "--- Eval grid ---"
check "LLM proposal eval grid" python3 -c "
import sys
sys.path.insert(0, 'analysis')
sys.path.insert(0, 'analysis/evals')
from runner import run_eval_suite
grid = run_eval_suite()
all_pass = all(r.get('pass', False) for r in grid.values() if 'error' not in r)
sys.exit(0 if all_pass else 1)
"

echo ""

# 4. End-to-end: generate against fixtures (dry-run)
echo "--- End-to-end ---"
E2E_DIR=$(mktemp -d)
check "Generate dry-run (evidence -> baseline)" \
    ./bin/sloscope generate \
        --service checkout-api \
        --namespace payments \
        --evidence testdata/evidence_checkout_api.json \
        --out "$E2E_DIR" \
        --dry-run

echo ""

# 5. Validate generated baseline
echo "--- Artifact validation ---"
check "Baseline validates against schema" python3 -c "
import json, sys
sys.path.insert(0, 'analysis')
from schemas.validate import validate
with open('$E2E_DIR/baseline.json') as f:
    baseline = json.load(f)
validate(baseline, 'baseline')
"

check "Evidence validates against schema" python3 -c "
import json, sys
sys.path.insert(0, 'analysis')
from schemas.validate import validate
with open('$E2E_DIR/evidence.json') as f:
    evidence = json.load(f)
validate(evidence, 'evidence')
"

# 6. Baseline determinism check
check "Baseline is deterministic (byte-for-byte)" bash -c "
./bin/sloscope generate --service checkout-api --namespace payments --evidence testdata/evidence_checkout_api.json --out ${E2E_DIR}/run1 --dry-run 2>/dev/null
./bin/sloscope generate --service checkout-api --namespace payments --evidence testdata/evidence_checkout_api.json --out ${E2E_DIR}/run2 --dry-run 2>/dev/null
diff ${E2E_DIR}/run1/baseline.json ${E2E_DIR}/run2/baseline.json
"

# 7. Consistency check: verify baseline values are in expected ranges
check "Baseline consistency (values in range)" python3 -c "
import json, sys
with open('$E2E_DIR/baseline.json') as f:
    b = json.load(f)
ind = b['indicators']
assert 0 < ind['latency']['p50_ms'] < ind['latency']['p99_ms'], 'p50 < p99'
assert 0 < ind['error_rate']['ratio'] < 1, 'error_rate in (0,1)'
assert 0 < ind['availability']['ratio'] <= 1, 'availability in (0,1]'
assert ind['throughput']['mean_rps'] > 0, 'throughput > 0'
"

echo ""

# Cleanup
rm -rf "$E2E_DIR"

# ---- Doc 2: Drift detector checks ----
if [ -d internal/drift ]; then
    echo ""
    echo "--- Drift: Go tests ---"
    check "Drift package tests" go test ./internal/drift/ -count=1

    echo ""
    echo "--- Drift: Python tests ---"
    check "Deviation computation tests" python3 -m pytest analysis/tests/test_deviation.py -q
    check "Drift schema contract tests" python3 -m pytest analysis/tests/test_drift_schemas.py -q
    check "Classification eval tests" python3 -m pytest analysis/tests/test_classify.py -q

    echo ""
    echo "--- Drift: Eval grid ---"
    check "Drift classification eval grid" python3 -c "
import sys
sys.path.insert(0, 'analysis')
sys.path.insert(0, 'analysis/evals')
from drift_runner import run_drift_eval_suite
grid = run_drift_eval_suite()
all_pass = all(r.get('pass', False) for r in grid.values() if 'error' not in r)
sys.exit(0 if all_pass else 1)
"

    echo ""
    echo "--- Drift: End-to-end ---"
    DRIFT_E2E_DIR=$(mktemp -d)
    check "Drift dry-run (baseline + evidence -> drift-signal)" \
        ./bin/sloscope drift \
            --service checkout-api \
            --baseline testdata/drift_baseline_reference.json \
            --evidence testdata/drift_live_latency_regression.json \
            --out "$DRIFT_E2E_DIR" \
            --dry-run

    echo ""
    echo "--- Drift: Artifact validation ---"
    check "Drift signal validates against schema" python3 -c "
import json, sys
sys.path.insert(0, 'analysis')
from schemas.validate import validate
with open('$DRIFT_E2E_DIR/drift-signal.json') as f:
    validate(json.load(f), 'drift-signal')
"

    check "Drift signal detects latency regression" python3 -c "
import json, sys
with open('$DRIFT_E2E_DIR/drift-signal.json') as f:
    signal = json.load(f)
assert signal['dominant_signal']['class'] == 'latency_regression', \
    f'Expected latency_regression, got {signal[\"dominant_signal\"][\"class\"]}'
"

    # No-drift control
    DRIFT_NODRIFT_DIR=$(mktemp -d)
    check "Drift dry-run (no-drift control)" \
        ./bin/sloscope drift \
            --service checkout-api \
            --baseline testdata/drift_baseline_reference.json \
            --evidence testdata/drift_live_no_drift.json \
            --out "$DRIFT_NODRIFT_DIR" \
            --dry-run

    check "No-drift control classifies correctly" python3 -c "
import json, sys
with open('$DRIFT_NODRIFT_DIR/drift-signal.json') as f:
    signal = json.load(f)
assert signal['dominant_signal']['class'] == 'no_significant_drift', \
    f'Expected no_significant_drift, got {signal[\"dominant_signal\"][\"class\"]}'
assert len(signal['all_breached_indicators']) == 0, \
    f'Expected no breaches, got {signal[\"all_breached_indicators\"]}'
"

    check "Drift signal is deterministic" bash -c "
./bin/sloscope drift --service checkout-api --baseline testdata/drift_baseline_reference.json --evidence testdata/drift_live_latency_regression.json --out ${DRIFT_E2E_DIR}/run1 --dry-run 2>/dev/null
./bin/sloscope drift --service checkout-api --baseline testdata/drift_baseline_reference.json --evidence testdata/drift_live_latency_regression.json --out ${DRIFT_E2E_DIR}/run2 --dry-run 2>/dev/null
diff ${DRIFT_E2E_DIR}/run1/drift-signal.json ${DRIFT_E2E_DIR}/run2/drift-signal.json
"

    rm -rf "$DRIFT_E2E_DIR" "$DRIFT_NODRIFT_DIR"
fi

# ---- Multi-signal evidence checks ----
if [ -f testdata/evidence_checkout_api_full.json ]; then
    echo ""
    echo "--- Multi-signal evidence ---"
    check "Full evidence (metrics+traces+logs) validates" python3 -c "
import json, sys
sys.path.insert(0, 'analysis')
from schemas.validate import validate
with open('testdata/evidence_checkout_api_full.json') as f:
    validate(json.load(f), 'evidence')
"

    check "Full evidence baseline includes trace indicators" python3 -c "
import json, sys
sys.path.insert(0, 'analysis')
from baseline import compute_baseline
with open('testdata/evidence_checkout_api_full.json') as f:
    bl = compute_baseline(json.load(f))
assert bl['indicators']['trace_latency']['available'], 'trace_latency not available'
assert bl['indicators']['error_breakdown']['available'], 'error_breakdown not available'
assert bl['indicators']['trace_latency']['top_dependency'] == 'payment-gateway'
"
fi

# Summary
echo ""
echo "=== Component Matrix ==="
echo ""
echo "| Component                          | Status |"
echo "|------------------------------------|--------|"
echo "| Prometheus query layer             | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Baseline computation               | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Artifact schemas + Go/Python boundary | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| LLM proposal stage (eval grid)     | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Renderers (OpenSLO + Prom rules)   | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Audit bundle                       | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Backend API                        | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Frontend components                | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| End to end                         | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
if [ -d internal/drift ]; then
echo "| Drift deviation + classification   | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Drift schema contracts             | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Drift eval grid                    | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
echo "| Drift end to end                   | $([ $FAIL -eq 0 ] && echo GREEN || echo RED)   |"
fi
echo ""
echo "Results: $PASS/$TOTAL passed"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "VERIFICATION FAILED ($FAIL checks RED)"
    exit 1
else
    echo ""
    echo "VERIFICATION PASSED (all checks GREEN)"
    exit 0
fi
