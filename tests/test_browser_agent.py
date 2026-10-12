"""
test_browser_agent.py — Integration tests for the JARVIS Browser Agent (Chunk 6).

All tests mock Playwright so no real browser or network is needed.
Run with: python -m pytest tests/test_browser_agent.py -v

NOTE: Both services/browser/main.py and services/orchestrator/main.py are named
'main'. pytest runs all test files in one process, so a bare `import main` grabs
whichever got cached first. We use importlib to load the browser module under a
unique name ('browser_service_main') to avoid this collision entirely.
"""

import sys
import os
import importlib.util
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Load browser service module explicitly under a unique name.
# This avoids the sys.modules["main"] collision with orchestrator/main.py.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BROWSER_MAIN_PATH = os.path.join(_REPO_ROOT, "services", "browser", "main.py")

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

def _load_browser_module():
    spec = importlib.util.spec_from_file_location("browser_service_main", _BROWSER_MAIN_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["browser_service_main"] = mod
    spec.loader.exec_module(mod)
    return mod

browser_main = _load_browser_module()

# Now import shared schemas (path already set above)
from shared.contracts.schemas import (
    BrowserSearchResult, BrowserSearchResponse, BrowserSearchRequest,
    BrowserActionRequest, BrowserActionResponse
)


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

class TestBrowserSchemas:
    """Tests that the new schema models validate correctly."""

    def test_browser_search_result_valid(self):
        r = BrowserSearchResult(
            title="Best Python Frameworks",
            url="https://example.com/python",
            snippet="A list of top Python web frameworks."
        )
        assert r.title == "Best Python Frameworks"
        assert r.url == "https://example.com/python"
        assert r.snippet is not None

    def test_browser_search_result_no_snippet(self):
        r = BrowserSearchResult(title="Title", url="https://x.com")
        assert r.snippet is None

    def test_browser_search_response_success(self):
        resp = BrowserSearchResponse(
            query="test query",
            results=[BrowserSearchResult(title="T", url="https://t.com")],
            success=True
        )
        assert resp.success is True
        assert len(resp.results) == 1

    def test_browser_search_response_failure(self):
        resp = BrowserSearchResponse(
            query="bad query",
            results=[],
            success=False,
            error="Search timed out"
        )
        assert resp.success is False
        assert "timed out" in resp.error

    def test_browser_action_request_search_action(self):
        req = BrowserActionRequest(action="search", query="python tutorials", max_results=3)
        assert req.action == "search"
        assert req.query == "python tutorials"
        assert req.max_results == 3

    def test_browser_action_request_navigate_action(self):
        req = BrowserActionRequest(action="navigate", url="https://example.com")
        assert req.action == "navigate"
        assert req.url == "https://example.com"

    def test_browser_action_response_with_search_results(self):
        resp = BrowserActionResponse(
            success=True,
            search_results=[
                BrowserSearchResult(title="Result 1", url="https://r1.com"),
                BrowserSearchResult(title="Result 2", url="https://r2.com"),
            ]
        )
        assert resp.success is True
        assert len(resp.search_results) == 2

    def test_browser_action_response_navigate(self):
        resp = BrowserActionResponse(
            success=True,
            page_title="Example Domain",
            extracted_text="This domain is for use in illustrative examples."
        )
        assert resp.page_title == "Example Domain"
        assert resp.search_results is None


# ---------------------------------------------------------------------------
# Browser agent endpoint tests (Playwright mocked)
# ---------------------------------------------------------------------------

class TestBrowserSearchEndpoint:
    """Tests the /api/v1/search endpoint with mocked Playwright."""

    def _mock_results(self, count: int = 3):
        return [
            BrowserSearchResult(
                title=f"Result {i+1}",
                url=f"https://example{i+1}.com",
                snippet=f"Snippet {i+1}."
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Successful search returns list of BrowserSearchResult."""
        mock_results = self._mock_results(3)

        with patch.object(browser_main, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results
            req = BrowserSearchRequest(query="best python frameworks", max_results=5)
            resp = await browser_main.search(req)

        assert resp.success is True
        assert len(resp.results) == 3
        assert resp.results[0].title == "Result 1"
        assert resp.query == "best python frameworks"
        mock_search.assert_called_once_with("best python frameworks", 5)

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_no_results(self):
        """Search returning empty list is still success=True."""
        with patch.object(browser_main, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            req = BrowserSearchRequest(query="xyzzy12345nonsense", max_results=5)
            resp = await browser_main.search(req)

        assert resp.success is True
        assert resp.results == []

    @pytest.mark.asyncio
    async def test_search_timeout_returns_error(self):
        """Timeout during search returns success=False with error message."""
        with patch.object(browser_main, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = asyncio.TimeoutError()
            req = BrowserSearchRequest(query="timeout test", max_results=5)
            resp = await browser_main.search(req)

        assert resp.success is False
        assert "timed out" in resp.error.lower()
        assert resp.results == []

    @pytest.mark.asyncio
    async def test_search_exception_returns_error(self):
        """Playwright crash returns success=False with the error string."""
        with patch.object(browser_main, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = RuntimeError("Chromium crashed")
            req = BrowserSearchRequest(query="crash test", max_results=5)
            resp = await browser_main.search(req)

        assert resp.success is False
        assert "Chromium crashed" in resp.error


class TestBrowserBrowseEndpoint:
    """Tests the /api/v1/browse endpoint with mocked Playwright."""

    @pytest.mark.asyncio
    async def test_navigate_action_returns_title_and_text(self):
        """navigate action returns page title and text excerpt."""
        with patch.object(browser_main, "_do_navigate", new_callable=AsyncMock) as mock_nav:
            mock_nav.return_value = ("Example Domain", "This domain is for illustrative examples.", "")
            req = BrowserActionRequest(action="navigate", url="https://example.com")
            resp = await browser_main.browse(req)

        assert resp.success is True
        assert resp.page_title == "Example Domain"
        assert "illustrative" in resp.extracted_text
        mock_nav.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_navigate_missing_url_returns_error(self):
        """navigate action without url returns success=False."""
        req = BrowserActionRequest(action="navigate")
        resp = await browser_main.browse(req)

        assert resp.success is False
        assert "url" in resp.error.lower()

    @pytest.mark.asyncio
    async def test_search_action_via_browse_endpoint(self):
        """search action via /browse endpoint returns search_results."""
        mock_results = [
            BrowserSearchResult(title="R1", url="https://r1.com"),
            BrowserSearchResult(title="R2", url="https://r2.com"),
        ]

        with patch.object(browser_main, "_do_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_results
            req = BrowserActionRequest(action="search", query="python tutorials")
            resp = await browser_main.browse(req)

        assert resp.success is True
        assert len(resp.search_results) == 2
        assert resp.search_results[0].title == "R1"

    @pytest.mark.asyncio
    async def test_search_action_missing_query_returns_error(self):
        """search action without query or url returns success=False."""
        req = BrowserActionRequest(action="search")
        resp = await browser_main.browse(req)

        assert resp.success is False
        assert "query" in resp.error.lower()

    @pytest.mark.asyncio
    async def test_screenshot_action_returns_path(self):
        """screenshot action returns file path."""
        with patch.object(browser_main, "_do_screenshot", new_callable=AsyncMock) as mock_ss:
            mock_ss.return_value = "/app/screenshots/screenshot_abc123.png"
            req = BrowserActionRequest(action="screenshot", url="https://example.com")
            resp = await browser_main.browse(req)

        assert resp.success is True
        assert resp.screenshot_path.endswith(".png")
        assert "screenshot_abc123" in resp.screenshot_path

    @pytest.mark.asyncio
    async def test_navigate_timeout_returns_error(self):
        """Timeout during navigate returns success=False."""
        with patch.object(browser_main, "_do_navigate", new_callable=AsyncMock) as mock_nav:
            mock_nav.side_effect = asyncio.TimeoutError()
            req = BrowserActionRequest(action="navigate", url="https://slow-site.com")
            resp = await browser_main.browse(req)

        assert resp.success is False
        assert "timed out" in resp.error.lower()

    @pytest.mark.asyncio
    async def test_unsupported_action_returns_error(self):
        """Unknown action returns success=False with helpful message."""
        req = BrowserActionRequest(action="fly_to_moon", url="https://moon.nasa.gov")
        resp = await browser_main.browse(req)

        assert resp.success is False
        assert "Unsupported action" in resp.error


# ---------------------------------------------------------------------------
# Health probe tests
# ---------------------------------------------------------------------------

class TestBrowserHealthProbes:
    """Tests liveness and readiness probes."""

    def test_healthz_returns_healthy(self):
        resp = browser_main.healthz()
        assert resp.status == "healthy"
        assert resp.service == "browser-service"
        assert resp.version == "2.0.0"

    def test_readyz_with_playwright_available(self):
        with patch.object(browser_main, "_playwright_available", return_value=True):
            resp = browser_main.readyz()
        assert resp.status == "ready"
        assert resp.checks["playwright_package"] == "ready"

    def test_readyz_playwright_not_installed(self):
        """When Playwright is missing, readyz should return not_ready (503)."""
        from fastapi.testclient import TestClient
        with patch.object(browser_main, "_playwright_available", return_value=False):
            client = TestClient(browser_main.app)
            resp = client.get("/readyz")
        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "not_ready"
