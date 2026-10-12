"""
test_planner_routing.py — Integration tests for orchestrator planner routing.

Tests the confidence gate, risk gate, and keyword fallback paths
without requiring a real Groq API key.

Run with: python -m pytest tests/test_planner_routing.py -v
"""

import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "orchestrator"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.contracts.schemas import PlannerOutput, PlannerFailure, TargetAgent, RiskLevel


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_planner_output(
    raw_input: str,
    intent: str,
    target_agent: str,
    action: str,
    target: str | None = None,
    confidence: float = 0.92,
    requires_confirmation: bool = False,
    risk_level: str = "low",
    reasoning: str = "Test."
) -> PlannerOutput:
    return PlannerOutput(
        schema_version="1.0",
        raw_user_input=raw_input,
        intent=intent,
        target_agent=target_agent,
        action=action,
        target=target,
        parameters={},
        confidence=confidence,
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
        reasoning_summary=reasoning
    )


def _make_planner_failure(raw_input: str, reason: str = "API key missing") -> PlannerFailure:
    return PlannerFailure(
        raw_user_input=raw_input,
        failure_reason=reason,
        retry_count=2,
        fallback_used=False
    )


# --------------------------------------------------------------------------- #
# Tests for orchestrator routing behavior
# --------------------------------------------------------------------------- #

class TestClassifyIntentAndRoute:
    """Tests the legacy keyword-based router (used as fallback)."""

    def test_open_app_routes_to_desktop(self):
        from main import classify_intent_and_route
        intent, agent = classify_intent_and_route("open notepad")
        assert agent == "desktop"
        assert intent == "open_app"

    def test_close_app_routes_to_desktop(self):
        from main import classify_intent_and_route
        intent, agent = classify_intent_and_route("close teams")
        assert agent == "desktop"
        assert intent == "close_app"

    def test_search_routes_to_browser(self):
        from main import classify_intent_and_route
        intent, agent = classify_intent_and_route("search best laptops")
        assert agent == "browser"
        assert intent == "search_web"

    def test_screenshot_routes_to_desktop(self):
        from main import classify_intent_and_route
        intent, agent = classify_intent_and_route("take a screenshot")
        assert agent == "desktop"
        assert intent == "screenshot"

    def test_folder_routes_to_desktop(self):
        from main import classify_intent_and_route
        intent, agent = classify_intent_and_route("open downloads folder")
        assert agent == "desktop"
        assert intent == "open_folder"

    def test_unknown_returns_orchestrator(self):
        from main import classify_intent_and_route
        intent, agent = classify_intent_and_route("xyzzy gibberish foobar")
        assert agent == "orchestrator"
        assert intent == "unknown"


class TestConfidenceGating:
    """Tests that confidence thresholds control routing behavior."""

    @pytest.mark.asyncio
    async def test_high_confidence_routes_to_execution(self):
        """Confidence >= 0.80 should route and attempt execution."""
        from main import coordinate
        from shared.contracts.schemas import ChatRequest

        planner_output = _make_planner_output(
            "open notepad", "open_app", "desktop", "open", "notepad", confidence=0.95
        )

        with patch("main.planner_service.plan", return_value=planner_output), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("Opened notepad.", [])
            request = ChatRequest(message="open notepad")
            response = await coordinate(request)

        assert "Opened" in response.response or "notepad" in response.response.lower()
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_medium_confidence_triggers_clarification(self):
        """Confidence between 0.50 and 0.79 should return clarification, not execute."""
        from main import coordinate
        from shared.contracts.schemas import ChatRequest

        planner_output = _make_planner_output(
            "open something", "open_app", "desktop", "open", "something", confidence=0.65,
            reasoning="User wants to open something, unclear target."
        )

        with patch("main.planner_service.plan", return_value=planner_output), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            request = ChatRequest(message="open something")
            response = await coordinate(request)

        mock_exec.assert_not_called()
        # Should ask for confirmation/clarification
        assert "confirm" in response.response.lower() or "rephrase" in response.response.lower() or "?" in response.response

    @pytest.mark.asyncio
    async def test_low_confidence_safely_rejects(self):
        """Confidence < 0.50 should safely reject without execution."""
        from main import coordinate
        from shared.contracts.schemas import ChatRequest

        planner_output = _make_planner_output(
            "zzz", "unknown", "unknown", "unknown", None, confidence=0.30,
            reasoning="Completely unclear."
        )

        with patch("main.planner_service.plan", return_value=planner_output), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            request = ChatRequest(message="zzz")
            response = await coordinate(request)

        mock_exec.assert_not_called()
        assert "confident" in response.response.lower() or "rephrase" in response.response.lower()


class TestRiskGating:
    """Tests that high-risk tasks are blocked pending confirmation."""

    @pytest.mark.asyncio
    async def test_high_risk_blocks_execution(self):
        """High-risk planner outputs must be blocked and stored for confirmation."""
        from main import coordinate, tasks_db
        from shared.contracts.schemas import ChatRequest

        planner_output = _make_planner_output(
            "delete all files in downloads",
            "system_control", "desktop", "delete", "downloads",
            confidence=0.91, requires_confirmation=True, risk_level="high",
            reasoning="Destructive action."
        )

        with patch("main.planner_service.plan", return_value=planner_output), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            request = ChatRequest(message="delete all files in downloads")
            response = await coordinate(request)

        mock_exec.assert_not_called()
        assert "CONFIRMATION" in response.response or "risk" in response.response.lower()

    @pytest.mark.asyncio
    async def test_medium_risk_executes_with_log_warning(self):
        """Medium-risk tasks should execute (with a log warning) but not be blocked."""
        from main import coordinate
        from shared.contracts.schemas import ChatRequest

        planner_output = _make_planner_output(
            "close notepad", "close_app", "desktop", "close", "notepad",
            confidence=0.88, risk_level="medium"
        )

        with patch("main.planner_service.plan", return_value=planner_output), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("Closed notepad.", [])
            request = ChatRequest(message="close notepad")
            response = await coordinate(request)

        mock_exec.assert_called_once()


class TestPlannerFallback:
    """Tests that keyword routing is used when planner fails."""

    @pytest.mark.asyncio
    async def test_planner_failure_uses_keyword_fallback(self):
        """When the planner returns PlannerFailure, keyword-based routing should take over."""
        from main import coordinate
        from shared.contracts.schemas import ChatRequest

        failure = _make_planner_failure("open notepad", reason="GROQ_API_KEY is not set")

        with patch("main.planner_service.plan", return_value=failure), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("Opened notepad via keyword fallback.", [])
            request = ChatRequest(message="open notepad")
            response = await coordinate(request)

        # Execution should still happen via keyword fallback
        mock_exec.assert_called_once()
        # The planner failure log should appear in actions_taken
        planner_log = next(
            (a for a in response.actions_taken if a.get("action") == "llm_planner"),
            None
        )
        assert planner_log is not None
        assert planner_log["status"] == "failed"

    @pytest.mark.asyncio
    async def test_planner_failure_log_shows_fallback_used(self):
        """PlannerFailure output in actions_taken should show fallback_used=True."""
        from main import coordinate
        from shared.contracts.schemas import ChatRequest

        failure = _make_planner_failure("open teams")

        with patch("main.planner_service.plan", return_value=failure), \
             patch("main.run_task_execution", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("Result.", [])
            request = ChatRequest(message="open teams")
            response = await coordinate(request)

        planner_log = next(
            (a for a in response.actions_taken if a.get("action") == "llm_planner"),
            None
        )
        assert planner_log is not None
        # After fallback, failure_output should show fallback_used = True
        assert planner_log["output"].get("fallback_used") is True
