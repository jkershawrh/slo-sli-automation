"""Adversarial evidence admission, independent of a live model or cluster."""
import copy
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evidence_constraints import EvidenceConstraintError, classification_constraints, proposal_constraints, proposal_claim_errors
from classify import classify, check_grounding
from propose import propose

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


def test_classification_binds_valid_evidence_to_digest():
    signal = load('evals/fixtures/drift/latency_regression.json')
    result = classification_constraints(signal)
    changed = copy.deepcopy(signal)
    changed['evaluated_at'] = '2026-10-20T00:00:00Z'
    assert classification_constraints(changed)['input_sha256'] != result['input_sha256']
    assert 'latency_p99_ms' in result['breached_indicators']


@pytest.mark.parametrize('mutation', ['empty','low_coverage','skipped','conflicting_breaches','nan'])
def test_insufficient_or_conflicting_input_abstains_before_model_call(mutation):
    signal = load('evals/fixtures/drift/latency_regression.json')
    if mutation == 'empty': signal['indicators'] = []
    if mutation == 'low_coverage': signal['provenance']['coverage_ratio'] = .79
    if mutation == 'skipped':
        for indicator in signal['indicators']: indicator['status'] = 'skipped'
    if mutation == 'conflicting_breaches': signal['all_breached_indicators'] = []
    if mutation == 'nan': signal['indicators'][0]['live_value'] = float('nan')
    client = MagicMock()
    with pytest.raises(EvidenceConstraintError): classify(signal, client=client, model='stub')
    client.chat.completions.create.assert_not_called()


def test_runtime_rejects_wrong_service_and_invented_numeric_proposal():
    baseline = load('evals/fixtures/web_api_baseline.json')
    proposal = load('evals/recorded/web_api_baseline_response.json')
    proposal['service'] = 'other-service'
    proposal['slos'][0]['headroom']['observed_value'] = 999999999
    proposal['slos'][0]['rationale'] = 'Observed 999999999 milliseconds from the dependency.'
    assert proposal_constraints(proposal, baseline)
    assert proposal_claim_errors(proposal, baseline)
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = json.dumps(proposal)
    with pytest.raises(RuntimeError): propose(baseline, client=client, model='stub')


def test_percent_multiplier_and_remediation_claims_cannot_bypass_grounding():
    signal = load('evals/fixtures/drift/latency_regression.json')
    report = load('evals/recorded/drift/latency_regression_response.json')
    assert not check_grounding(report, signal)
    report['recommendations'][0]['remediation_plan']['evidence_basis'] = 'Observed 999999% error rate and 999999x regression'
    assert check_grounding(report, signal)


def test_throughput_is_not_an_availability_boundary():
    from consistency import check_consistency
    baseline = load('evals/fixtures/web_api_baseline.json')
    proposal = load('evals/recorded/web_api_baseline_response.json')
    row = proposal['slos'][0]
    row.update(sli_type='throughput', target_op='gte', slo_target=1, sla_target=10)
    assert check_consistency(proposal, baseline)


def test_remediation_plan_cannot_hide_executable_commands():
    from classify import check_actuation
    report=load('evals/recorded/drift/latency_regression_response.json')
    report['recommendations'][0]['remediation_plan']['verification_method']='kubectl delete pod checkout-api'
    assert check_actuation(report)


@pytest.mark.parametrize('field,value',[('direction','decreasing'),('first_pass_class','error_rate_elevation')])
def test_conflicting_indicator_class_or_direction_abstains(field,value):
    signal=load('evals/fixtures/drift/latency_regression.json')
    signal['indicators'][0][field]=value
    with pytest.raises(EvidenceConstraintError): classification_constraints(signal)


@pytest.mark.parametrize('citation',['.123456789','999,999,999','9.99e12'])
def test_alternate_numeric_notation_cannot_hide_fabricated_measurements(citation):
    signal=load('evals/fixtures/drift/latency_regression.json')
    report=load('evals/recorded/drift/latency_regression_response.json')
    report['likely_cause']='Observed '+citation+' milliseconds.'
    assert check_grounding(report,signal)


@pytest.mark.parametrize("identity", ["service", "namespace"])
def test_drift_rejects_cross_identity_observations(identity):
    from baseline import compute_baseline
    from deviation import compute_drift_signal
    evidence = json.loads((ROOT.parent / "testdata/evidence_checkout_api.json").read_text())
    reference = compute_baseline(evidence)
    evidence[identity] = "different"
    with pytest.raises(EvidenceConstraintError, match="identities do not match"):
        compute_drift_signal({"baseline": reference, "live_evidence": evidence})
