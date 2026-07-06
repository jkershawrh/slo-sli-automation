"""EDD tests for the LLM proposal stage."""

import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evals.rubric import (
    check_budget_coherence,
    check_consistency,
    check_grounding,
    check_indicator_appropriateness,
    check_rationale_quality,
    evaluate_proposal,
    extract_baseline_values,
)
from evals.runner import load_fixture, load_recorded_response, run_eval_suite
from consistency import (
    check_consistency as propose_check_consistency,
    check_consistency_bool,
    check_margin_quality,
    check_direction_validity,
)
from propose import propose

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "evals" / "fixtures"
RECORDED_DIR = Path(__file__).resolve().parent.parent / "evals" / "recorded"
FIXTURE_NAMES = ["web_api_baseline", "high_traffic_baseline", "batch_processor_baseline"]


def _load_baseline(name):
    with open(FIXTURES_DIR / "{}.json".format(name)) as f:
        return json.load(f)


def _load_response(name):
    with open(RECORDED_DIR / "{}_response.json".format(name)) as f:
        return json.load(f)


def _make_mock_response(content):
    """Build a mock OpenAI ChatCompletion response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ---------------------------------------------------------------------------
# Test: Rubric Hard Gates
# ---------------------------------------------------------------------------


class TestRubricHardGates:
    """Test that hard gates correctly identify pass/fail."""

    def test_valid_proposal_passes_schema(self):
        proposal = _load_response("web_api_baseline")
        assert evaluate_proposal(proposal, _load_baseline("web_api_baseline"))[
            "hard_gates"
        ]["schema_validity"] is True

    def test_invalid_schema_fails(self):
        # Missing required 'slos' field
        bad_proposal = {"schema_version": 1, "service": "test"}
        baseline = _load_baseline("web_api_baseline")
        result = evaluate_proposal(bad_proposal, baseline)
        assert result["hard_gates"]["schema_validity"] is False
        assert result["pass"] is False

    def test_grounding_passes_when_rationale_cites_baseline(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        assert check_grounding(proposal, baseline) is True

    def test_grounding_fails_when_rationale_has_no_baseline_numbers(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        # Replace all rationales with text that has no baseline numbers
        bad_proposal = copy.deepcopy(proposal)
        for slo in bad_proposal["slos"]:
            slo["rationale"] = "This SLO is important for the business."
        assert check_grounding(bad_proposal, baseline) is False

    def test_consistency_passes_when_target_not_tighter(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        assert check_consistency(proposal, baseline) is True

    def test_consistency_fails_when_latency_target_tighter_without_flag(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        bad_proposal = copy.deepcopy(proposal)
        # Set sla_target below observed p99 (500ms) — SLA must not be tighter than observed
        for slo in bad_proposal["slos"]:
            if slo["sli_type"] == "latency":
                slo["sla_target"] = 200.0
                slo["requires_review"] = False
        assert check_consistency(bad_proposal, baseline) is False

    def test_consistency_passes_when_tighter_with_review_flag(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        flagged_proposal = copy.deepcopy(proposal)
        for slo in flagged_proposal["slos"]:
            if slo["sli_type"] == "latency":
                slo["target"] = 200.0
                slo["requires_review"] = True
                slo["review_reason"] = "Tighter target for business needs"
        assert check_consistency(flagged_proposal, baseline) is True

    def test_consistency_fails_when_availability_target_higher_without_flag(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        bad_proposal = copy.deepcopy(proposal)
        # Observed availability is 0.998; sla_target higher than observed is tighter (wrong for SLA)
        for slo in bad_proposal["slos"]:
            if slo["sli_type"] == "availability":
                slo["sla_target"] = 0.9999
                slo["requires_review"] = False
        assert check_consistency(bad_proposal, baseline) is False


# ---------------------------------------------------------------------------
# Test: Rubric Scored Dimensions
# ---------------------------------------------------------------------------


class TestRubricScoredDimensions:
    """Test scored dimensions."""

    def test_indicator_appropriateness_passes_with_latency_and_availability(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        assert check_indicator_appropriateness(proposal, baseline) is True

    def test_indicator_appropriateness_fails_without_latency(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        no_latency = copy.deepcopy(proposal)
        no_latency["slos"] = [
            s for s in no_latency["slos"] if s["sli_type"] != "latency"
        ]
        assert check_indicator_appropriateness(no_latency, baseline) is False

    def test_indicator_appropriateness_fails_without_error_or_availability(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        no_avail = copy.deepcopy(proposal)
        no_avail["slos"] = [
            s
            for s in no_avail["slos"]
            if s["sli_type"] not in ("availability", "error_rate")
        ]
        assert check_indicator_appropriateness(no_avail, baseline) is False

    def test_budget_coherence_passes_with_valid_budgets(self):
        proposal = _load_response("web_api_baseline")
        assert check_budget_coherence(proposal) is True

    def test_budget_coherence_fails_with_zero_budget(self):
        proposal = _load_response("web_api_baseline")
        bad = copy.deepcopy(proposal)
        bad["slos"][0]["error_budget_percent"] = 0
        assert check_budget_coherence(bad) is False

    def test_budget_coherence_fails_with_no_windows(self):
        proposal = _load_response("web_api_baseline")
        bad = copy.deepcopy(proposal)
        bad["slos"][0]["burn_rate_policy"]["windows"] = []
        assert check_budget_coherence(bad) is False

    def test_budget_coherence_fails_with_zero_burn_rate(self):
        proposal = _load_response("web_api_baseline")
        bad = copy.deepcopy(proposal)
        bad["slos"][0]["burn_rate_policy"]["windows"][0]["burn_rate"] = 0
        assert check_budget_coherence(bad) is False

    def test_rationale_quality_passes_with_baseline_values(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        assert check_rationale_quality(proposal, baseline) is True

    def test_rationale_quality_fails_with_empty_rationale(self):
        proposal = _load_response("web_api_baseline")
        baseline = _load_baseline("web_api_baseline")
        bad = copy.deepcopy(proposal)
        # Schema requires minLength 1, but we can put non-numeric text
        bad["slos"][0]["rationale"] = "No numbers here at all."
        assert check_rationale_quality(bad, baseline) is False


# ---------------------------------------------------------------------------
# Test: Extract baseline values
# ---------------------------------------------------------------------------


class TestExtractBaselineValues:
    """Test the baseline value extraction utility."""

    def test_extracts_latency_values(self):
        baseline = _load_baseline("web_api_baseline")
        values = extract_baseline_values(baseline)
        assert 500.0 in values  # p99
        assert 120.0 in values  # p50

    def test_extracts_error_rate(self):
        baseline = _load_baseline("web_api_baseline")
        values = extract_baseline_values(baseline)
        assert 0.002 in values  # error ratio

    def test_extracts_availability(self):
        baseline = _load_baseline("web_api_baseline")
        values = extract_baseline_values(baseline)
        assert 0.998 in values  # availability ratio


# ---------------------------------------------------------------------------
# Test: Full Eval Grid
# ---------------------------------------------------------------------------


class TestEvalGrid:
    """Test the full eval grid against recorded responses."""

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_recorded_response_passes_all_gates(self, fixture_name):
        baseline = _load_baseline(fixture_name)
        proposal = _load_response(fixture_name)
        result = evaluate_proposal(proposal, baseline)
        assert result["pass"] is True, (
            "Fixture {} failed: hard_gates={}, scored={}".format(
                fixture_name, result["hard_gates"], result["scored_dimensions"]
            )
        )

    def test_all_recorded_responses_pass_via_runner(self):
        grid = run_eval_suite()
        for fixture_name, result in grid.items():
            assert result.get("pass") is True, (
                "Runner grid failed for {}: {}".format(fixture_name, result)
            )


# ---------------------------------------------------------------------------
# Test: Repair Loop (mocked OpenAI client)
# ---------------------------------------------------------------------------


class TestRepairLoop:
    """Test the LLM repair loop (mocked)."""

    def test_valid_first_response_succeeds(self):
        baseline = _load_baseline("web_api_baseline")
        valid_response = _load_response("web_api_baseline")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            json.dumps(valid_response)
        )

        result = propose(baseline, client=mock_client, model="test-model")
        assert result["schema_version"] == 3
        assert len(result["slos"]) >= 1
        # Should only have been called once
        assert mock_client.chat.completions.create.call_count == 1

    def test_invalid_json_retries(self):
        baseline = _load_baseline("web_api_baseline")
        valid_response = _load_response("web_api_baseline")

        mock_client = MagicMock()
        # First call: invalid JSON; second call: valid JSON
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response("this is not json {{{"),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = propose(baseline, client=mock_client, model="test-model")
        assert result["schema_version"] == 3
        assert mock_client.chat.completions.create.call_count == 2

    def test_max_retries_exceeded_raises(self):
        baseline = _load_baseline("web_api_baseline")

        mock_client = MagicMock()
        # All calls return invalid JSON (MAX_RETRIES + 1 = 4 calls)
        mock_client.chat.completions.create.return_value = _make_mock_response(
            "not json at all"
        )

        with pytest.raises(RuntimeError, match="failed to produce valid JSON"):
            propose(baseline, client=mock_client, model="test-model")

        assert mock_client.chat.completions.create.call_count == 4  # 1 + 3 retries

    def test_schema_invalid_retries_then_succeeds(self):
        baseline = _load_baseline("web_api_baseline")
        valid_response = _load_response("web_api_baseline")

        # Build a schema-invalid but parseable JSON response
        invalid_proposal = {"schema_version": 1, "service": "test"}  # missing slos

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(json.dumps(invalid_proposal)),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = propose(baseline, client=mock_client, model="test-model")
        assert result["schema_version"] == 3
        assert mock_client.chat.completions.create.call_count == 2

    def test_consistency_error_retries_then_succeeds(self):
        baseline = _load_baseline("web_api_baseline")
        valid_response = _load_response("web_api_baseline")

        # Build a response that is schema-valid but consistency-invalid
        inconsistent = copy.deepcopy(valid_response)
        for slo in inconsistent["slos"]:
            if slo["sli_type"] == "latency":
                slo["sla_target"] = 100.0  # tighter than p99 of 500ms
                slo["requires_review"] = False

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(json.dumps(inconsistent)),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = propose(baseline, client=mock_client, model="test-model")
        assert result["schema_version"] == 3
        assert mock_client.chat.completions.create.call_count == 2

    def test_markdown_fenced_json_is_stripped(self):
        baseline = _load_baseline("web_api_baseline")
        valid_response = _load_response("web_api_baseline")
        fenced = "```json\n{}\n```".format(json.dumps(valid_response))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(fenced)

        result = propose(baseline, client=mock_client, model="test-model")
        assert result["schema_version"] == 3


# ---------------------------------------------------------------------------
# Test: Consistency Checker (propose.py)
# ---------------------------------------------------------------------------


class TestConsistencyCheck:
    """Test the consistency checker in propose.py."""

    def test_latency_target_tighter_than_p99_fails(self):
        baseline = _load_baseline("web_api_baseline")
        proposal = _load_response("web_api_baseline")
        bad = copy.deepcopy(proposal)
        for slo in bad["slos"]:
            if slo["sli_type"] == "latency":
                slo["sla_target"] = 200.0  # tighter than 500ms p99
                slo["requires_review"] = False
        errors = propose_check_consistency(bad, baseline)
        assert len(errors) > 0
        assert "latency" in errors[0].lower()

    def test_availability_target_higher_than_observed_fails(self):
        baseline = _load_baseline("web_api_baseline")
        proposal = _load_response("web_api_baseline")
        bad = copy.deepcopy(proposal)
        for slo in bad["slos"]:
            if slo["sli_type"] == "availability":
                slo["sla_target"] = 0.9999  # higher than observed 0.998
                slo["requires_review"] = False
        errors = propose_check_consistency(bad, baseline)
        assert len(errors) > 0
        assert "availability" in errors[0].lower()

    def test_error_rate_target_lower_than_observed_fails(self):
        baseline = _load_baseline("web_api_baseline")
        # Build a proposal with an error_rate SLO
        proposal = copy.deepcopy(_load_response("web_api_baseline"))
        proposal["slos"].append(
            {
                "sli_name": "error_rate_slo",
                "sli_type": "error_rate",
                "sli_definition": "Error rate of requests",
                "target": 0.0001,  # tighter than observed 0.002
                "target_op": "lte",
                "target_unit": "ratio",
                "error_budget_percent": 0.1,
                "burn_rate_policy": {
                    "windows": [
                        {
                            "long_window": "1h",
                            "short_window": "5m",
                            "burn_rate": 14.4,
                            "severity": "critical",
                        },
                        {
                            "long_window": "6h",
                            "short_window": "30m",
                            "burn_rate": 6.0,
                            "severity": "warning",
                        },
                    ]
                },
                "rationale": "Error rate based on observed 0.002 ratio.",
                "requires_review": False,
            }
        )
        errors = propose_check_consistency(proposal, baseline)
        assert len(errors) > 0
        assert "error_rate" in errors[0].lower()

    def test_consistent_proposal_has_no_errors(self):
        baseline = _load_baseline("web_api_baseline")
        proposal = _load_response("web_api_baseline")
        errors = propose_check_consistency(proposal, baseline)
        assert errors == []

    def test_tighter_target_with_review_flag_passes(self):
        baseline = _load_baseline("web_api_baseline")
        proposal = _load_response("web_api_baseline")
        flagged = copy.deepcopy(proposal)
        for slo in flagged["slos"]:
            if slo["sli_type"] == "latency":
                slo["target"] = 200.0
                slo["requires_review"] = True
                slo["review_reason"] = "Business requirement"
        errors = propose_check_consistency(flagged, baseline)
        assert errors == []


# ---------------------------------------------------------------------------
# Test: Fixture schema validation
# ---------------------------------------------------------------------------


class TestFixtureValidity:
    """Verify all fixtures validate against their schemas."""

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_baseline_fixture_validates(self, fixture_name):
        from schemas.validate import validate

        baseline = _load_baseline(fixture_name)
        validate(baseline, "baseline")  # raises on failure

    @pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
    def test_recorded_response_validates(self, fixture_name):
        from schemas.validate import validate

        proposal = _load_response(fixture_name)
        validate(proposal, "proposal")  # raises on failure


# ---------------------------------------------------------------------------
# Test: New consistency and margin checks
# ---------------------------------------------------------------------------


class TestNewConsistencyChecks:
    """Test the new consistency, margin, and direction checks."""

    def test_wrong_target_op_fails_consistency(self):
        """A latency SLO with target_op='gte' should fail direction check."""
        baseline = _load_baseline("web_api_baseline")
        proposal = copy.deepcopy(_load_response("web_api_baseline"))
        for slo in proposal["slos"]:
            if slo["sli_type"] == "latency":
                slo["target_op"] = "gte"  # wrong: latency should be lte
        errors = propose_check_consistency(proposal, baseline)
        assert len(errors) > 0
        assert any("target_op" in e for e in errors)

    def test_excessively_loose_target_fails(self):
        """An sla_target >5 stddev above observed should fail consistency."""
        baseline = _load_baseline("web_api_baseline")
        proposal = copy.deepcopy(_load_response("web_api_baseline"))
        for slo in proposal["slos"]:
            if slo["sli_type"] == "latency":
                # p99=500ms, stddev=95ms; 50000ms is >5 stddev loose
                slo["sla_target"] = 50000.0
        errors = propose_check_consistency(proposal, baseline)
        assert len(errors) > 0
        assert any("excessively loose" in e for e in errors)

    def test_target_equals_observed_fails(self):
        """A target equal to observed should fail the margin check."""
        baseline = _load_baseline("web_api_baseline")
        proposal = copy.deepcopy(_load_response("web_api_baseline"))
        for slo in proposal["slos"]:
            if slo["sli_type"] == "latency":
                slo["slo_target"] = 500.0  # exactly equals observed p99
                slo["sla_target"] = 500.0  # exactly equals observed p99
        assert check_margin_quality(proposal, baseline) is False

    def test_margin_quality_passes_with_headroom(self):
        """A proposal with proper headroom should pass margin check."""
        baseline = _load_baseline("web_api_baseline")
        proposal = _load_response("web_api_baseline")
        # The recorded response already has proper headroom
        assert check_margin_quality(proposal, baseline) is True

    def test_direction_validity_passes_for_recorded(self):
        """All recorded responses should have correct target_op."""
        for fixture_name in FIXTURE_NAMES:
            proposal = _load_response(fixture_name)
            assert check_direction_validity(proposal) is True, (
                "Direction validity failed for {}".format(fixture_name)
            )

    def test_direction_validity_fails_with_wrong_op(self):
        """Availability SLO with target_op='lte' should fail direction check."""
        proposal = copy.deepcopy(_load_response("web_api_baseline"))
        for slo in proposal["slos"]:
            if slo["sli_type"] == "availability":
                slo["target_op"] = "lte"  # wrong: availability should be gte
        assert check_direction_validity(proposal) is False
