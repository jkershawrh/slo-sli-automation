"""EDD tests for the LLM drift classification and remediation stage."""

import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from evals.drift_rubric import (
    check_class_validity,
    check_classification_accuracy,
    check_grounding,
    check_no_actuation,
    check_rationale_quality,
    check_remediation_relevance,
    check_severity_calibration,
    evaluate_drift_report,
    extract_signal_values,
)
from evals.drift_runner import (
    load_drift_fixture,
    load_drift_recorded_response,
    load_ground_truth,
    run_drift_eval_suite,
    DRIFT_SCENARIOS,
)
from classify import (
    check_actuation,
    check_class_consistency,
    check_grounding as classify_check_grounding,
    check_severity_consistency,
    classify,
    extract_signal_values as classify_extract_values,
    normalized_report_class,
    MAX_RETRIES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "evals" / "fixtures" / "drift"
RECORDED_DIR = Path(__file__).resolve().parent.parent / "evals" / "recorded" / "drift"


def _load_fixture(name):
    with open(FIXTURES_DIR / "{}.json".format(name)) as f:
        return json.load(f)


def _load_response(name):
    with open(RECORDED_DIR / "{}_response.json".format(name)) as f:
        return json.load(f)


def _load_gt():
    with open(FIXTURES_DIR / "ground_truth.json") as f:
        return json.load(f)


def _make_mock_response(content):
    """Build a mock OpenAI ChatCompletion response."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ---------------------------------------------------------------------------
# Test 1: All recorded responses pass the drift rubric (eval grid green)
# ---------------------------------------------------------------------------


class TestEvalGridGreen:
    """All recorded responses must pass every hard gate and scored dimension."""

    @pytest.mark.parametrize("scenario", DRIFT_SCENARIOS)
    def test_recorded_response_passes_rubric(self, scenario):
        signal = _load_fixture(scenario)
        response = _load_response(scenario)
        gt = _load_gt()[scenario]
        result = evaluate_drift_report(response, signal, gt)
        assert result["pass"] is True, (
            "Scenario {} failed: hard_gates={}, scored={}".format(
                scenario, result["hard_gates"], result["scored_dimensions"]
            )
        )

    def test_full_eval_suite_via_runner(self):
        grid = run_drift_eval_suite()
        for scenario, result in grid.items():
            assert result.get("pass") is True, (
                "Runner grid failed for {}: {}".format(scenario, result)
            )


# ---------------------------------------------------------------------------
# Test 2: Schema validation catches invalid responses
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Schema validity hard gate catches invalid drift reports."""

    def test_valid_report_passes_schema(self):
        response = _load_response("latency_regression")
        signal = _load_fixture("latency_regression")
        gt = _load_gt()["latency_regression"]
        result = evaluate_drift_report(response, signal, gt)
        assert result["hard_gates"]["schema_validity"] is True

    def test_missing_required_field_fails_schema(self):
        # Missing 'recommendations' field
        bad_report = {
            "schema_version": 1,
            "service": "test",
            "classification": "latency_regression",
            "severity": "high",
            "likely_cause": "test cause",
        }
        signal = _load_fixture("latency_regression")
        gt = _load_gt()["latency_regression"]
        result = evaluate_drift_report(bad_report, signal, gt)
        assert result["hard_gates"]["schema_validity"] is False
        assert result["pass"] is False

    def test_invalid_classification_enum_fails_schema(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["classification"] = "not_a_valid_class"
        signal = _load_fixture("latency_regression")
        gt = _load_gt()["latency_regression"]
        result = evaluate_drift_report(response, signal, gt)
        assert result["hard_gates"]["schema_validity"] is False

    def test_invalid_severity_enum_fails_schema(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["severity"] = "extreme"
        signal = _load_fixture("latency_regression")
        gt = _load_gt()["latency_regression"]
        result = evaluate_drift_report(response, signal, gt)
        assert result["hard_gates"]["schema_validity"] is False


# ---------------------------------------------------------------------------
# Test 3: Grounding check catches invented numbers
# ---------------------------------------------------------------------------


class TestGroundingCheck:
    """Grounding hard gate catches numbers not present in drift signals."""

    def test_grounded_report_passes(self):
        response = _load_response("latency_regression")
        signal = _load_fixture("latency_regression")
        assert check_grounding(response, signal) is True

    def test_invented_number_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        # Add an invented number to the likely cause
        response["likely_cause"] = (
            "The latency increased to 999999.0 ms, which is very bad."
        )
        signal = _load_fixture("latency_regression")
        assert check_grounding(response, signal) is False

    def test_classify_grounding_catches_invented(self):
        """Test the grounding check in classify.py module."""
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["rationale"] = (
            "The deviation of 42424.0 is alarming."
        )
        signal = _load_fixture("latency_regression")
        errors = classify_check_grounding(response, signal)
        assert len(errors) > 0
        assert "42424" in errors[0]


# ---------------------------------------------------------------------------
# Test 4: Class validity catches wrong taxonomy entries
# ---------------------------------------------------------------------------


class TestClassValidity:
    """Class validity hard gate catches invalid taxonomy entries."""

    def test_valid_class_passes(self):
        response = _load_response("latency_regression")
        signal = _load_fixture("latency_regression")
        assert check_class_validity(response, signal) is True

    def test_non_taxonomy_class_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["classification"] = "memory_leak"
        signal = _load_fixture("latency_regression")
        # This would also fail schema validation, but class_validity
        # checks independently
        assert check_class_validity(response, signal) is False


# ---------------------------------------------------------------------------
# Test 5: Class consistency catches contradicting dominant signal
# ---------------------------------------------------------------------------


class TestClassConsistency:
    """Class consistency catches classes that contradict the dominant signal."""

    def test_consistent_class_passes(self):
        response = _load_response("latency_regression")
        signal = _load_fixture("latency_regression")
        assert check_class_validity(response, signal) is True

    def test_contradicting_class_fails(self):
        # Dominant signal is latency_regression, but report says throughput_collapse
        response = copy.deepcopy(_load_response("latency_regression"))
        response["classification"] = "throughput_collapse"
        signal = _load_fixture("latency_regression")
        assert check_class_validity(response, signal) is False

    def test_distribution_shift_allowed_for_latency_regression(self):
        # distribution_shift is a valid refinement of latency_regression
        response = copy.deepcopy(_load_response("latency_regression"))
        response["classification"] = "distribution_shift"
        signal = _load_fixture("latency_regression")
        assert check_class_validity(response, signal) is True

    def test_classify_consistency_check_rejects_contradiction(self):
        """Test the consistency checker in classify.py."""
        response = copy.deepcopy(_load_response("error_rate_elevation"))
        response["classification"] = "latency_regression"
        signal = _load_fixture("error_rate_elevation")
        errors = check_class_consistency(response, signal)
        assert len(errors) > 0
        assert "inconsistent" in errors[0].lower()

    def test_dependency_refinement_normalizes_to_latency_regression(self):
        signal = _load_fixture("latency_regression")
        signal["dominant_signal"]["class"] = "dependency_latency_regression"
        assert normalized_report_class(signal) == "latency_regression"

        response = _load_response("latency_regression")
        errors = check_class_consistency(response, signal)
        assert errors == []

    def test_error_category_refinement_normalizes_to_error_rate_elevation(self):
        signal = _load_fixture("error_rate_elevation")
        signal["dominant_signal"]["class"] = "error_category_shift"
        signal["indicators"][0]["first_pass_class"] = "error_category_shift"
        signal["indicators"][0]["band_breach"] = True
        assert normalized_report_class(signal) == "error_rate_elevation"

        response = _load_response("error_rate_elevation")
        errors = check_class_consistency(response, signal)
        assert errors == []

    def test_error_category_mixed_breaches_normalizes_to_distribution_shift(self):
        signal = _load_fixture("error_rate_elevation")
        signal["dominant_signal"]["class"] = "error_category_shift"
        signal["indicators"][0]["first_pass_class"] = "error_category_shift"
        signal["indicators"][0]["band_breach"] = True
        signal["indicators"][1]["first_pass_class"] = "latency_regression"
        signal["indicators"][1]["band_breach"] = True
        assert normalized_report_class(signal) == "distribution_shift"


# ---------------------------------------------------------------------------
# Test 6: No-actuation check catches kubectl commands
# ---------------------------------------------------------------------------


class TestNoActuationKubectl:
    """No-actuation hard gate catches kubectl and similar commands."""

    def test_clean_report_passes(self):
        response = _load_response("latency_regression")
        assert check_no_actuation(response) is True

    def test_kubectl_in_action_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            "Run kubectl rollout restart deployment/checkout-api"
        )
        assert check_no_actuation(response) is False

    def test_oc_command_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            "Execute oc get pods -n checkout to check pod status"
        )
        assert check_no_actuation(response) is False

    def test_curl_command_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["rationale"] = (
            "Test with curl http://checkout-api/health"
        )
        assert check_no_actuation(response) is False

    def test_docker_command_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["likely_cause"] = (
            "You should docker pull the latest image"
        )
        assert check_no_actuation(response) is False

    def test_helm_command_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            "Use helm upgrade to deploy the fix"
        )
        assert check_no_actuation(response) is False

    def test_classify_actuation_check(self):
        """Test the actuation checker in classify.py."""
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            "Run kubectl scale deployment/checkout-api --replicas=3"
        )
        errors = check_actuation(response)
        assert len(errors) > 0
        assert "kubectl" in errors[0].lower()


# ---------------------------------------------------------------------------
# Test 7: No-actuation check catches YAML code blocks
# ---------------------------------------------------------------------------


class TestNoActuationYAML:
    """No-actuation hard gate catches YAML and JSON code blocks."""

    def test_yaml_block_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            "Apply this config:\n```yaml\napiVersion: v1\nkind: ConfigMap\n```"
        )
        assert check_no_actuation(response) is False

    def test_yml_block_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["rationale"] = (
            "See:\n```yml\nspec:\n  replicas: 3\n```"
        )
        assert check_no_actuation(response) is False

    def test_json_block_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            'Apply:\n```json\n{"replicas": 3}\n```'
        )
        assert check_no_actuation(response) is False

    def test_api_call_pattern_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["action"] = (
            "POST https://api.example.com/v1/restart"
        )
        assert check_no_actuation(response) is False


# ---------------------------------------------------------------------------
# Test 8: Repair loop works (mock OpenAI client)
# ---------------------------------------------------------------------------


class TestRepairLoop:
    """Test the LLM repair loop in classify.py (mocked)."""

    def test_valid_first_response_succeeds(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            json.dumps(valid_response)
        )

        result = classify(signal, client=mock_client, model="test-model")
        assert result["schema_version"] == 1
        assert result["classification"] == "latency_regression"
        assert mock_client.chat.completions.create.call_count == 1

    def test_explicit_context_argument_overrides_env(self, monkeypatch):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")

        monkeypatch.setenv("SLOSCOPE_CONTEXT_TYPE", "service")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            json.dumps(valid_response)
        )

        classify(signal, client=mock_client, model="test-model", context_type="infra")

        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        user_content = messages[1]["content"]
        assert "Context: infra" in user_content

    def test_invalid_json_retries_then_succeeds(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response("this is not json {{{"),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = classify(signal, client=mock_client, model="test-model")
        assert result["classification"] == "latency_regression"
        assert mock_client.chat.completions.create.call_count == 2

    def test_schema_invalid_retries_then_succeeds(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")

        # Schema-invalid but parseable JSON (missing recommendations)
        invalid_report = {
            "schema_version": 1,
            "service": "test",
            "classification": "latency_regression",
            "severity": "high",
            "likely_cause": "test",
        }

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(json.dumps(invalid_report)),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = classify(signal, client=mock_client, model="test-model")
        assert result["classification"] == "latency_regression"
        assert mock_client.chat.completions.create.call_count == 2

    def test_consistency_error_retries_then_succeeds(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")

        # Schema-valid but inconsistent (wrong class for dominant signal)
        inconsistent = copy.deepcopy(valid_response)
        inconsistent["classification"] = "throughput_collapse"

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(json.dumps(inconsistent)),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = classify(signal, client=mock_client, model="test-model")
        assert result["classification"] == "latency_regression"
        assert mock_client.chat.completions.create.call_count == 2

    def test_markdown_fenced_json_is_stripped(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")
        fenced = "```json\n{}\n```".format(json.dumps(valid_response))

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            fenced
        )

        result = classify(signal, client=mock_client, model="test-model")
        assert result["classification"] == "latency_regression"

    def test_actuation_error_retries_then_succeeds(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")

        # Report with kubectl command triggers actuation rejection
        bad_response = copy.deepcopy(valid_response)
        bad_response["recommendations"][0]["action"] = (
            "Run kubectl rollout restart deployment/checkout-api"
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _make_mock_response(json.dumps(bad_response)),
            _make_mock_response(json.dumps(valid_response)),
        ]

        result = classify(signal, client=mock_client, model="test-model")
        assert result["classification"] == "latency_regression"
        assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# Test 9: Max retries exceeded raises clear error
# ---------------------------------------------------------------------------


class TestMaxRetriesExceeded:
    """Max retries must raise RuntimeError with a clear message."""

    def test_all_invalid_json_raises(self):
        signal = _load_fixture("latency_regression")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            "not json at all"
        )

        with pytest.raises(RuntimeError, match="failed to produce valid JSON"):
            classify(signal, client=mock_client, model="test-model")

        # 1 initial + 3 retries = 4
        assert mock_client.chat.completions.create.call_count == MAX_RETRIES + 1

    def test_all_schema_invalid_raises(self):
        signal = _load_fixture("latency_regression")
        bad_report = {"schema_version": 1, "service": "test"}

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            json.dumps(bad_report)
        )

        with pytest.raises(RuntimeError, match="failed schema validation"):
            classify(signal, client=mock_client, model="test-model")

        assert mock_client.chat.completions.create.call_count == MAX_RETRIES + 1

    def test_all_inconsistent_raises(self):
        signal = _load_fixture("latency_regression")
        valid_response = _load_response("latency_regression")
        inconsistent = copy.deepcopy(valid_response)
        inconsistent["classification"] = "throughput_collapse"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_mock_response(
            json.dumps(inconsistent)
        )

        with pytest.raises(RuntimeError, match="failed consistency check"):
            classify(signal, client=mock_client, model="test-model")

        assert mock_client.chat.completions.create.call_count == MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# Test 10: Classification accuracy scoring works
# ---------------------------------------------------------------------------


class TestClassificationAccuracy:
    """Classification accuracy scored dimension."""

    def test_correct_class_passes(self):
        response = _load_response("latency_regression")
        gt = _load_gt()["latency_regression"]
        assert check_classification_accuracy(response, gt) is True

    def test_wrong_class_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["classification"] = "error_rate_elevation"
        gt = _load_gt()["latency_regression"]
        assert check_classification_accuracy(response, gt) is False

    def test_no_drift_correct_class(self):
        response = _load_response("no_significant_drift")
        gt = _load_gt()["no_significant_drift"]
        assert check_classification_accuracy(response, gt) is True

    @pytest.mark.parametrize("scenario", DRIFT_SCENARIOS)
    def test_all_recorded_responses_match_ground_truth(self, scenario):
        response = _load_response(scenario)
        gt = _load_gt()[scenario]
        assert check_classification_accuracy(response, gt) is True


# ---------------------------------------------------------------------------
# Test 11: Severity calibration scoring works
# ---------------------------------------------------------------------------


class TestSeverityCalibration:
    """Severity calibration scored dimension."""

    def test_severity_in_range_passes(self):
        response = _load_response("latency_regression")
        gt = _load_gt()["latency_regression"]
        assert check_severity_calibration(response, gt) is True

    def test_severity_out_of_range_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["severity"] = "info"  # expected ["high", "critical"]
        gt = _load_gt()["latency_regression"]
        assert check_severity_calibration(response, gt) is False

    def test_no_drift_severity_info(self):
        response = _load_response("no_significant_drift")
        gt = _load_gt()["no_significant_drift"]
        assert check_severity_calibration(response, gt) is True

    def test_improvement_severity_low_passes(self):
        response = copy.deepcopy(_load_response("latency_improvement"))
        response["severity"] = "low"
        gt = _load_gt()["latency_improvement"]
        assert check_severity_calibration(response, gt) is True

    def test_improvement_severity_critical_fails(self):
        response = copy.deepcopy(_load_response("latency_improvement"))
        response["severity"] = "critical"
        gt = _load_gt()["latency_improvement"]
        assert check_severity_calibration(response, gt) is False

    @pytest.mark.parametrize("scenario", DRIFT_SCENARIOS)
    def test_all_recorded_severities_in_range(self, scenario):
        response = _load_response(scenario)
        gt = _load_gt()[scenario]
        assert check_severity_calibration(response, gt) is True


# ---------------------------------------------------------------------------
# Test: Remediation relevance
# ---------------------------------------------------------------------------


class TestRemediationRelevance:
    """Remediation relevance scored dimension."""

    def test_performance_recommendation_matches(self):
        response = _load_response("latency_regression")
        gt = _load_gt()["latency_regression"]
        assert check_remediation_relevance(response, gt) is True

    def test_no_drift_recommendation_matches(self):
        response = _load_response("no_significant_drift")
        gt = _load_gt()["no_significant_drift"]
        assert check_remediation_relevance(response, gt) is True

    @pytest.mark.parametrize("scenario", DRIFT_SCENARIOS)
    def test_all_recorded_remediation_relevant(self, scenario):
        response = _load_response(scenario)
        gt = _load_gt()[scenario]
        assert check_remediation_relevance(response, gt) is True


# ---------------------------------------------------------------------------
# Test: Rationale quality
# ---------------------------------------------------------------------------


class TestRationaleQuality:
    """Rationale quality scored dimension."""

    def test_rationale_with_numbers_passes(self):
        response = _load_response("latency_regression")
        signal = _load_fixture("latency_regression")
        assert check_rationale_quality(response, signal) is True

    def test_rationale_without_numbers_fails(self):
        response = copy.deepcopy(_load_response("latency_regression"))
        response["recommendations"][0]["rationale"] = (
            "This is a generic rationale with no specific numbers."
        )
        signal = _load_fixture("latency_regression")
        assert check_rationale_quality(response, signal) is False


# ---------------------------------------------------------------------------
# Test: Fixture schema validation
# ---------------------------------------------------------------------------


class TestFixtureValidity:
    """Verify all drift fixtures and responses validate against schemas."""

    @pytest.mark.parametrize("scenario", DRIFT_SCENARIOS)
    def test_drift_signal_fixture_validates(self, scenario):
        from schemas.validate import validate
        signal = _load_fixture(scenario)
        validate(signal, "drift-signal")

    @pytest.mark.parametrize("scenario", DRIFT_SCENARIOS)
    def test_drift_report_response_validates(self, scenario):
        from schemas.validate import validate
        response = _load_response(scenario)
        validate(response, "drift-report")


# ---------------------------------------------------------------------------
# Test: Extract signal values
# ---------------------------------------------------------------------------


class TestExtractSignalValues:
    """Test the signal value extraction utility."""

    def test_extracts_live_values(self):
        signal = _load_fixture("latency_regression")
        values = extract_signal_values(signal)
        assert 750.0 in values  # live p99
        assert 500.0 in values  # baseline p99

    def test_extracts_band_boundaries(self):
        signal = _load_fixture("latency_regression")
        values = extract_signal_values(signal)
        assert 690.0 in values  # band_upper for p99
        assert 310.0 in values  # band_lower for p99

    def test_extracts_breach_magnitude(self):
        signal = _load_fixture("latency_regression")
        values = extract_signal_values(signal)
        assert 1.3158 in values  # breach magnitude


# ---------------------------------------------------------------------------
# Test: Classify module helpers
# ---------------------------------------------------------------------------


class TestClassifyHelpers:
    """Test classify.py utility functions."""

    def test_severity_consistency_no_breach_high_severity(self):
        report = {"severity": "critical", "classification": "no_significant_drift"}
        signal = {"dominant_signal": {"breach_magnitude": 0, "class": "no_significant_drift"}}
        errors = check_severity_consistency(report, signal)
        assert len(errors) > 0

    def test_severity_consistency_large_breach_info(self):
        report = {"severity": "info", "classification": "latency_regression"}
        signal = {"dominant_signal": {"breach_magnitude": 5.0, "class": "latency_regression"}}
        errors = check_severity_consistency(report, signal)
        assert len(errors) > 0

    def test_severity_consistency_improvement_critical(self):
        report = {"severity": "critical", "classification": "latency_improvement"}
        signal = {"dominant_signal": {"breach_magnitude": 1.0, "class": "latency_improvement"}}
        errors = check_severity_consistency(report, signal)
        assert len(errors) > 0

    def test_severity_consistency_valid(self):
        report = {"severity": "high", "classification": "latency_regression"}
        signal = {"dominant_signal": {"breach_magnitude": 1.3, "class": "latency_regression"}}
        errors = check_severity_consistency(report, signal)
        assert len(errors) == 0
