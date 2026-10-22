"""Live paths cannot become recorded success or replace a frozen reference."""
import copy
import json
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis'))
sys.path.insert(0, str(ROOT / 'backend'))
import collector
import server
from store import ArtifactStore
from fastapi.testclient import TestClient


def test_live_mode_never_falls_back_on_model_failure(monkeypatch):
    import propose
    def fail(*args, **kwargs): raise RuntimeError('model unavailable')
    monkeypatch.setattr(propose, 'propose', fail)
    monkeypatch.setenv('LLM_BASE_URL','http://model.test/v1')
    monkeypatch.setenv('LLM_API_KEY','test-only')
    baseline = json.loads((ROOT/'analysis/evals/fixtures/web_api_baseline.json').read_text())
    with TestClient(server.app) as client:
        response=client.post('/api/v1/propose',json={'baseline':baseline})
        assert response.status_code==502
        fixture=client.post('/api/v1/propose',json={'baseline':baseline,'mode':'fixture'})
        assert fixture.status_code==200 and fixture.headers['X-SLOscope-Mode']=='fixture'


def test_missing_or_insufficient_evidence_abstains_in_http(monkeypatch):
    signal=json.loads((ROOT/'analysis/evals/fixtures/drift/no_significant_drift.json').read_text())
    signal['indicators']=[]
    with TestClient(server.app) as client:
        response=client.post('/api/v1/drift/classify',json={'drift_signal':signal})
        assert response.status_code==422
        assert response.json()['detail']['status']=='abstained'


@pytest.mark.parametrize('field,value', [('rel_deviation', 999), ('breach_magnitude', 0)])
def test_http_rejects_fabricated_derived_evidence_without_calling_model(monkeypatch, field, value):
    import classify
    model = Mock(side_effect=AssertionError('invalid evidence reached model'))
    monkeypatch.setattr(classify, 'classify', model)
    monkeypatch.setenv('LLM_BASE_URL', 'http://must-not-be-called.test/v1')
    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    signal = json.loads((ROOT/'analysis/evals/fixtures/drift/latency_regression.json').read_text())
    target = signal['indicators'][0] if field == 'rel_deviation' else signal['dominant_signal']
    target[field] = value
    with TestClient(server.app) as client:
        response = client.post('/api/v1/drift/classify', json={'drift_signal': signal})
    assert response.status_code == 422
    assert response.json()['detail']['status'] == 'abstained'
    model.assert_not_called()


def test_collection_preserves_prior_baseline(tmp_path,monkeypatch):
    from baseline import compute_baseline
    evidence=json.loads((ROOT/'testdata/evidence_checkout_api.json').read_text())
    store=ArtifactStore(tmp_path)
    reference=compute_baseline(evidence)
    store.save('checkout-api','baseline',reference)
    current=copy.deepcopy(evidence)
    current['series']['error_total']['total'] *= 2
    monkeypatch.setattr(collector,'collect_evidence',lambda *args:current)
    result=collector.collect_and_store('checkout-api','payments',store)
    assert result['reference']=='preserved'
    assert store.load('checkout-api','baseline')==reference
    assert store.load('checkout-api','current-baseline')['indicators']['error_rate']['ratio'] != reference['indicators']['error_rate']['ratio']


def test_render_rejects_nonexistent_histogram_bucket():
    proposal=json.loads((ROOT/'analysis/evals/recorded/web_api_baseline_response.json').read_text())
    evidence=json.loads((ROOT/'testdata/evidence_checkout_api.json').read_text())
    with TestClient(server.app) as client:
        response=client.post('/api/v1/render',json={'proposal':proposal,'service':'checkout-api','evidence':evidence})
        assert response.status_code==422
        assert 'not an observed histogram bucket' in response.json()['detail']


def test_fresh_server_store_does_not_seed_recorded_data(tmp_path):
    import os
    import subprocess
    env = dict(os.environ, SLOSCOPE_STORE_DIR=str(tmp_path))
    env.pop('SLOSCOPE_SEED_DEMO', None)
    code = "from backend.server import store, health; assert store.list_services() == []; assert health()['artifact_mode'] == 'stored'"
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, check=True, capture_output=True)


def test_explicit_evidence_fixture_is_labeled():
    with TestClient(server.app) as client:
        response = client.post('/api/v1/evidence', json={'mode': 'fixture'})
        assert response.status_code == 200
        assert response.headers['X-SLOscope-Mode'] == 'fixture'
        assert response.headers['X-SLOscope-Input-SHA256']


def test_http_drift_abstains_on_cross_namespace_reference():
    from baseline import compute_baseline
    evidence = json.loads((ROOT / "testdata/evidence_checkout_api.json").read_text())
    reference = compute_baseline(evidence)
    evidence["namespace"] = "different"
    with TestClient(server.app) as client:
        response = client.post("/api/v1/drift/signal", json={"baseline": reference, "live_evidence": evidence})
        assert response.status_code == 422
        assert response.json()["detail"]["status"] == "abstained"
