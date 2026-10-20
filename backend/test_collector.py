"""Operator lookback reaches the collector, with no model or network dependency."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import collector

@pytest.mark.parametrize('value', ['1s', '119s', '31d', '0h', '-5m', '5m;echo bad', '1.5h', '1h30m', ' 5m'])
def test_lookback_rejects_invalid_or_unbounded(monkeypatch, value):
    monkeypatch.setenv('SLOSCOPE_LOOKBACK', value)
    with pytest.raises(ValueError, match='SLOSCOPE_LOOKBACK'):
        collector.configured_lookback()

@pytest.mark.parametrize('value', ['120s', '5m', '1h', '30d'])
def test_lookback_accepts_bounded_integer_interval(monkeypatch, value):
    monkeypatch.setenv('SLOSCOPE_LOOKBACK', value)
    assert collector.configured_lookback() == value


def test_default_lookback_is_one_hour(monkeypatch):
    monkeypatch.delenv('SLOSCOPE_LOOKBACK', raising=False)
    assert collector.configured_lookback() == '1h'


def test_collect_passes_operator_window_and_checks_returned_window(monkeypatch):
    evidence = json.loads((Path(__file__).parents[1] / 'testdata/evidence_checkout_api.json').read_text())
    evidence['lookback_window'] = '2m'
    monkeypatch.setenv('SLOSCOPE_LOOKBACK', '120s')
    def run(command, **kwargs):
        assert command[command.index('--lookback') + 1] == '120s'
        Path(command[command.index('--out') + 1], 'evidence.json').write_text(json.dumps(evidence))
    monkeypatch.setattr(collector.subprocess, 'run', run)
    assert collector.collect_evidence('checkout-api', 'payments')['lookback_window'] == '2m'
    evidence['lookback_window'] = '1h'
    with pytest.raises(ValueError, match='different lookback'):
        collector.collect_evidence('checkout-api', 'payments')
