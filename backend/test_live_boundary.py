"""Live paths cannot become recorded success or replace a frozen reference."""
import copy
import json
from pathlib import Path
import sys

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
