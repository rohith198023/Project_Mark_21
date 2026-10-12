"""
test_planner_service.py — Unit tests for the LLM Planner Service.

All tests mock the Groq API so no real API key is needed.
Run with: python -m pytest tests/test_planner_service.py -v
"""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock

# Ensure the orchestrator service is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.contracts.schemas import PlannerOutput, PlannerFailure, TargetAgent, RiskLevel


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_planner_json(
    raw_input: str,
    intent: str,
    target_agent: str,
    action: str,
    target: str | None,
    confidence: float = 0.92,
    requires_confirmation: bool = False,
    risk_level: str = "low",
    reasoning: str = "Test planner output."
) -> str:
    """Builds a valid planner JSON string to use as a mocked Groq response."""
    return json.dumps({
        "schema_version": "1.0",
        "raw_user_input": raw_input,
        "intent": intent,
        "target_agent": target_agent,
        "action": action,
        "target": target,
        "parameters": {},
        "confidence": confidence,
        "requires_confirmation": requires_confirmation,
        "risk_level": risk_level,
        "reasoning_summary": reasoning
    })


def _mock_groq_response(content: str):
    """Wraps a string in a mocked Groq chat completion response object."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    return mock_completion


# --------------------------------------------------------------------------- #
# Planner output parsing and validation tests
# --------------------------------------------------------------------------- #

class TestPlannerOutputValidation:
    """Tests that PlannerOutput validates correctly."""

    def test_valid_open_app(self):
        data = {
            "schema_version": "1.0",
            "raw_user_input": "open notepad",
            "intent": "open_app",
            "target_agent": "desktop",
            "action": "open",
            "target": "notepad",
            "parameters": {},
            "confidence": 0.95,
            "requires_confirmation": False,
            "risk_level": "low",
            "reasoning_summary": "User wants to open Notepad."
        }
        output = PlannerOutput.model_validate(data)
        assert output.intent == "open_app"
        assert output.target_agent == TargetAgent.DESKTOP
        assert output.risk_level == RiskLevel.LOW
        assert output.confidence == 0.95

    def test_confidence_out_of_range_raises(self):
        from pydantic import ValidationError
        data = {
            "schema_version": "1.0", "raw_user_input": "test",
            "intent": "open_app", "target_agent": "desktop", "action": "open",
            "target": None, "parameters": {}, "confidence": 1.5,
            "requires_confirmation": False, "risk_level": "low",
            "reasoning_summary": None
        }
        with pytest.raises(ValidationError):
            PlannerOutput.model_validate(data)

    def test_empty_raw_input_raises(self):
        from pydantic import ValidationError
        data = {
            "schema_version": "1.0", "raw_user_input": "",
            "intent": "open_app", "target_agent": "desktop", "action": "open",
            "target": None, "parameters": {}, "confidence": 0.9,
            "requires_confirmation": False, "risk_level": "low",
            "reasoning_summary": None
        }
        with pytest.raises(ValidationError):
            PlannerOutput.model_validate(data)

    def test_extra_fields_rejected(self):
        from pydantic import ValidationError
        data = {
            "schema_version": "1.0", "raw_user_input": "open notepad",
            "intent": "open_app", "target_agent": "desktop", "action": "open",
            "target": "notepad", "parameters": {}, "confidence": 0.9,
            "requires_confirmation": False, "risk_level": "low",
            "reasoning_summary": None,
            "unexpected_field": "should_fail"  # extra field
        }
        with pytest.raises(ValidationError):
            PlannerOutput.model_validate(data)

    def test_invalid_target_agent_raises(self):
        from pydantic import ValidationError
        data = {
            "schema_version": "1.0", "raw_user_input": "open notepad",
            "intent": "open_app", "target_agent": "flying_pig",  # invalid
            "action": "open", "target": "notepad", "parameters": {},
            "confidence": 0.9, "requires_confirmation": False,
            "risk_level": "low", "reasoning_summary": None
        }
        with pytest.raises(ValidationError):
            PlannerOutput.model_validate(data)

    def test_invalid_risk_level_raises(self):
        from pydantic import ValidationError
        data = {
            "schema_version": "1.0", "raw_user_input": "open notepad",
            "intent": "open_app", "target_agent": "desktop", "action": "open",
            "target": "notepad", "parameters": {}, "confidence": 0.9,
            "requires_confirmation": False, "risk_level": "critical",  # invalid
            "reasoning_summary": None
        }
        with pytest.raises(ValidationError):
            PlannerOutput.model_validate(data)


# --------------------------------------------------------------------------- #
# Planner service end-to-end tests (Groq mocked)
# --------------------------------------------------------------------------- #

class TestPlannerServiceIntents:
    """Tests all required intent scenarios with mocked Groq API."""

    def _run_plan(self, raw_input: str, mock_json: str) -> PlannerOutput:
        """Helper to run planner_service.plan() with a mocked Groq response."""
        import planner_service
        mock_completion = _mock_groq_response(mock_json)

        # Patch GROQ_API_KEY via environment variable (property has no setter)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key_mock"}), \
             patch("groq.Groq") as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_completion

            result = planner_service.plan(raw_input)

        assert isinstance(result, PlannerOutput), f"Expected PlannerOutput, got {type(result)}: {result}"
        return result

    def test_open_downloads_folder(self):
        raw = "open downloads folder"
        j = _make_planner_json(raw, "open_folder", "desktop", "open", "downloads")
        result = self._run_plan(raw, j)
        assert result.intent == "open_folder"
        assert result.target_agent == TargetAgent.DESKTOP
        assert result.target == "downloads"
        assert result.risk_level == RiskLevel.LOW

    def test_open_file_manager(self):
        raw = "open file manager"
        j = _make_planner_json(raw, "open_app", "desktop", "open", "file_explorer")
        result = self._run_plan(raw, j)
        assert result.intent == "open_app"
        assert result.target == "file_explorer"

    def test_open_my_files(self):
        raw = "open my files"
        j = _make_planner_json(raw, "open_app", "desktop", "open", "file_explorer")
        result = self._run_plan(raw, j)
        assert result.target_agent == TargetAgent.DESKTOP

    def test_open_notepad(self):
        raw = "open notepad"
        j = _make_planner_json(raw, "open_app", "desktop", "open", "notepad")
        result = self._run_plan(raw, j)
        assert result.intent == "open_app"
        assert result.target == "notepad"

    def test_open_teams(self):
        raw = "open teams"
        j = _make_planner_json(raw, "open_app", "desktop", "open", "teams")
        result = self._run_plan(raw, j)
        assert result.intent == "open_app"
        assert result.target == "teams"

    def test_open_microsoft_store(self):
        raw = "open microsoft store"
        j = _make_planner_json(raw, "open_app", "desktop", "open", "microsoft store", confidence=0.95)
        result = self._run_plan(raw, j)
        assert result.target_agent == TargetAgent.DESKTOP

    def test_search_web(self):
        raw = "search best laptops under 50000"
        j = _make_planner_json(raw, "search_web", "browser", "search", "best laptops under 50000")
        result = self._run_plan(raw, j)
        assert result.intent == "search_web"
        assert result.target_agent == TargetAgent.BROWSER
        assert "laptop" in result.target.lower()

    def test_screenshot(self):
        raw = "take screenshot of current page"
        j = _make_planner_json(raw, "screenshot", "desktop", "screenshot", None)
        result = self._run_plan(raw, j)
        assert result.intent == "screenshot"
        assert result.target_agent == TargetAgent.DESKTOP

    def test_close_notepad(self):
        raw = "close notepad"
        j = _make_planner_json(raw, "close_app", "desktop", "close", "notepad",
                                confidence=0.88, risk_level="medium")
        result = self._run_plan(raw, j)
        assert result.intent == "close_app"
        assert result.risk_level == RiskLevel.MEDIUM
        assert not result.requires_confirmation  # medium risk doesn't auto-require confirmation

    def test_high_risk_requires_confirmation(self):
        raw = "delete all files in downloads"
        j = _make_planner_json(raw, "system_control", "desktop", "delete", "downloads",
                                confidence=0.91, requires_confirmation=True, risk_level="high",
                                reasoning="Destructive action detected.")
        result = self._run_plan(raw, j)
        assert result.risk_level == RiskLevel.HIGH
        assert result.requires_confirmation is True


# --------------------------------------------------------------------------- #
# Retry and failure tests
# --------------------------------------------------------------------------- #

class TestPlannerRetry:
    """Tests retry logic and failure handling."""

    def test_retry_on_invalid_json(self):
        """Planner should retry on bad JSON and succeed on second attempt."""
        import planner_service

        valid_json = _make_planner_json(
            "open notepad", "open_app", "desktop", "open", "notepad"
        )
        bad_response = _mock_groq_response("this is not json at all")
        good_response = _mock_groq_response(valid_json)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}), \
             patch("groq.Groq") as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            # First call returns bad JSON, second returns valid
            mock_client.chat.completions.create.side_effect = [bad_response, good_response]
            result = planner_service.plan("open notepad", max_retries=2)

        assert isinstance(result, PlannerOutput)
        assert result.intent == "open_app"

    def test_all_retries_exhausted_returns_failure(self):
        """After all retries fail, should return PlannerFailure."""
        import planner_service

        bad_response = _mock_groq_response("not json")

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}), \
             patch("groq.Groq") as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_client.chat.completions.create.return_value = bad_response

            result = planner_service.plan("open notepad", max_retries=2)

        assert isinstance(result, PlannerFailure)
        assert result.retry_count == 2
        assert "non-JSON" in result.failure_reason or "JSON" in result.failure_reason

    def test_missing_api_key_returns_failure(self):
        """Missing API key should return PlannerFailure immediately without retry."""
        import planner_service

        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            result = planner_service.plan("open notepad", max_retries=2)

        assert isinstance(result, PlannerFailure)
        assert "GROQ_API_KEY" in result.failure_reason

    def test_markdown_fence_stripped(self):
        """Planner should handle LLM adding markdown fences around JSON."""
        import planner_service

        valid_json = _make_planner_json(
            "open notepad", "open_app", "desktop", "open", "notepad"
        )
        fenced = f"```json\n{valid_json}\n```"
        mock_completion = _mock_groq_response(fenced)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}), \
             patch("groq.Groq") as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_completion

            result = planner_service.plan("open notepad")

        assert isinstance(result, PlannerOutput)
        assert result.intent == "open_app"

    def test_empty_response_returns_failure(self):
        """Empty LLM response should return PlannerFailure."""
        import planner_service

        mock_completion = _mock_groq_response("")

        with patch.dict(os.environ, {"GROQ_API_KEY": "test_key"}), \
             patch("groq.Groq") as MockGroq:
            mock_client = MagicMock()
            MockGroq.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_completion

            result = planner_service.plan("test", max_retries=0)

        assert isinstance(result, PlannerFailure)
