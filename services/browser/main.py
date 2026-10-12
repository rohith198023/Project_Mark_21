"""
services/browser/main.py — JARVIS Browser Agent (Phase 2, Chunk 6)

Provides real headless Chromium execution via Playwright for:
  - search_web  → Google SERP scrape, returns top N result titles + URLs
  - navigate    → Navigate to a URL, return page title + visible text excerpt
  - screenshot  → Capture full-page screenshot, return file path

All endpoints conform to the BrowserActionRequest / BrowserActionResponse
schema contracts defined in shared/contracts/schemas.py.
"""

import os
import sys
import uuid
import logging
import asyncio
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Ensure shared modules are importable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.contracts.schemas import (
    BrowserActionRequest, BrowserActionResponse,
    BrowserSearchRequest, BrowserSearchResponse,
    BrowserSearchResult,
    HealthResponse, ReadinessResponse
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("browser-service")

app = FastAPI(
    title="JARVIS Browser Service",
    description="Headless Chromium browser automation agent powered by Playwright.",
    version="2.0.0"
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "/app/screenshots")
BROWSER_TIMEOUT_MS = int(os.getenv("BROWSER_TIMEOUT_MS", "25000"))   # 25s
BROWSER_NAV_WAIT = int(os.getenv("BROWSER_NAV_WAIT", "8000"))        # 8s
MAX_TEXT_CHARS = 2500  # Maximum visible text to return for navigate actions

# Google search URL template
GOOGLE_SEARCH_URL = "https://www.google.com/search?q={query}&hl=en&num=10"

# CSS selectors for Google SERP result blocks
GOOGLE_RESULT_SELECTOR = "div.g"
GOOGLE_TITLE_SELECTOR = "h3"
GOOGLE_LINK_SELECTOR = "a[href]"
GOOGLE_SNIPPET_SELECTOR = ".VwiC3b, .s3v9rd, span[data-ved]"


# ---------------------------------------------------------------------------
# Playwright availability check (used by /readyz)
# ---------------------------------------------------------------------------

def _playwright_available() -> bool:
    """Returns True if the playwright package and Chromium binary are available."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        # Check if the chromium executable exists
        from playwright._impl._driver import compute_driver_executable
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal browser helpers (async Playwright)
# ---------------------------------------------------------------------------

async def _do_search(query: str, max_results: int) -> List[BrowserSearchResult]:
    """
    Opens Google search for `query` and extracts up to `max_results` organic results.
    If Google blocks or returns 0 results, falls back to DuckDuckGo HTML.
    Returns a list of BrowserSearchResult (title, url, snippet).
    """
    from playwright.async_api import async_playwright

    results: List[BrowserSearchResult] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        await page.add_init_script("delete navigator.__proto__.webdriver;")

        try:
            # --- 1. BING SEARCH (Fast, reliable, and unblocked in Docker) ---
            bing_url = f"https://www.bing.com/search?q={query.replace(' ', '+')}"
            logger.info(f"[Browser] Searching Bing: '{query}' (max={max_results})")
            try:
                await page.goto(bing_url, wait_until="domcontentloaded", timeout=8000)
                await page.wait_for_timeout(600)
                result_elements = await page.query_selector_all("li.b_algo")
                logger.info(f"[Browser] Found {len(result_elements)} results on Bing")

                for el in result_elements:
                    if len(results) >= max_results:
                        break

                    title_el = await el.query_selector("h2 a, h3 a, h2, h3")
                    if title_el:
                        title = (await title_el.text_content() or "").strip()
                        href = await title_el.get_attribute("href")
                        if not href:
                            anchor = await title_el.query_selector("a")
                            href = await anchor.get_attribute("href") if anchor else None

                        if not title or not href or not href.startswith("http"):
                            continue

                        snippet_el = await el.query_selector(".b_caption p, .b_lineLimit, p")
                        snippet = (await snippet_el.inner_text()).strip() if snippet_el else None

                        results.append(BrowserSearchResult(
                            title=title,
                            url=href,
                            snippet=snippet[:300] if snippet else None
                        ))
            except Exception as bing_err:
                logger.warning(f"[Browser] Bing search failed: {bing_err}")

            # --- 2. DUCKDUCKGO HTML FALLBACK ---
            if len(results) == 0:
                logger.warning(f"[Browser] Bing returned 0 results. Trying DuckDuckGo HTML fallback...")
                ddg_html_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
                try:
                    await page.goto(ddg_html_url, wait_until="domcontentloaded", timeout=7000)
                    await page.wait_for_timeout(500)

                    result_elements = await page.query_selector_all("div.result")
                    logger.info(f"[Browser] Found {len(result_elements)} results on DuckDuckGo HTML")

                    for el in result_elements:
                        if len(results) >= max_results:
                            break

                        title_el = await el.query_selector("a.result__a")
                        if title_el:
                            title = (await title_el.text_content() or "").strip()
                            href = await title_el.get_attribute("href")

                            if href and href.startswith("//"):
                                href = f"https:{href}"

                            if not title or not href or not href.startswith("http") or "duckduckgo.com/y.js" in href:
                                continue

                            snippet_el = await el.query_selector("a.result__snippet")
                            snippet = (await snippet_el.inner_text()).strip() if snippet_el else None

                            results.append(BrowserSearchResult(
                                title=title,
                                url=href,
                                snippet=snippet[:300] if snippet else None
                            ))
                except Exception as ddg_html_err:
                    logger.warning(f"[Browser] DuckDuckGo HTML fallback failed: {ddg_html_err}")

            # --- 3. GOOGLE FALLBACK ---
            if len(results) == 0:
                logger.warning(f"[Browser] Fallbacks returned 0 results. Trying Google...")
                google_url = GOOGLE_SEARCH_URL.format(query=query.replace(" ", "+"))
                try:
                    await page.goto(google_url, wait_until="domcontentloaded", timeout=7000)
                    await page.wait_for_timeout(1000)
                    result_elements = await page.query_selector_all(GOOGLE_RESULT_SELECTOR)
                    logger.info(f"[Browser] Found {len(result_elements)} raw Google result blocks")

                    for el in result_elements:
                        if len(results) >= max_results:
                            break

                        title_el = await el.query_selector(GOOGLE_TITLE_SELECTOR)
                        title = (await title_el.text_content() or "").strip() if title_el else ""

                        link_el = await el.query_selector(GOOGLE_LINK_SELECTOR)
                        href = await link_el.get_attribute("href") if link_el else ""

                        if not title or not href or not href.startswith("http"):
                            continue

                        snippet_el = await el.query_selector(GOOGLE_SNIPPET_SELECTOR)
                        snippet = (await snippet_el.inner_text()).strip() if snippet_el else None

                        results.append(BrowserSearchResult(
                            title=title,
                            url=href,
                            snippet=snippet[:300] if snippet else None
                        ))
                except Exception as g_err:
                    logger.warning(f"[Browser] Google search failed: {g_err}")

            # --- DEBUG SIGNALS IF STILL 0 ---
            if len(results) == 0:
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                debug_path = os.path.join(SCREENSHOTS_DIR, "debug_search_fail.png")
                try:
                    await page.screenshot(path=debug_path)
                    logger.error(
                        f"[Browser] All search fallback paths returned 0 results. "
                        f"Saved debug screenshot to: '{debug_path}'. "
                        f"Page Title: '{await page.title()}'. URL: '{page.url}'"
                    )
                except Exception as ss_err:
                    logger.error(f"[Browser] All searches returned 0, and failed to write debug screenshot: {ss_err}")

            logger.info(f"[Browser] Total extracted search results: {len(results)}")

        finally:
            await browser.close()

    return results


async def _do_navigate(url: str) -> tuple[str, str, str]:
    """
    Navigates to `url` with headless Chromium.
    Returns (page_title, text_excerpt, screenshot_path_or_empty).
    """
    from playwright.async_api import async_playwright

    logger.info(f"[Browser] Navigating to: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
            await page.wait_for_timeout(1000)

            title = await page.title()

            # Extract visible text (body inner text, trimmed)
            body_text = await page.inner_text("body")
            text_excerpt = " ".join(body_text.split())[:MAX_TEXT_CHARS]

            logger.info(f"[Browser] Loaded page: '{title}' ({len(text_excerpt)} chars)")
            return title, text_excerpt, ""

        finally:
            await browser.close()


async def _do_screenshot(url: Optional[str]) -> str:
    """
    Takes a full-page screenshot of `url` (or current page if url is None).
    Saves it to SCREENSHOTS_DIR and returns the file path.
    """
    from playwright.async_api import async_playwright

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    filename = f"screenshot_{uuid.uuid4().hex[:10]}.png"
    filepath = os.path.join(SCREENSHOTS_DIR, filename)

    target_url = url or "about:blank"
    logger.info(f"[Browser] Taking screenshot of: {target_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        try:
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1000)
            await page.screenshot(path=filepath, full_page=True)
            logger.info(f"[Browser] Screenshot saved to: {filepath}")
        finally:
            await browser.close()

    return filepath


# ---------------------------------------------------------------------------
# Health probes
# ---------------------------------------------------------------------------

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe."""
    return HealthResponse(status="healthy", service="browser-service", version="2.0.0")


@app.get("/readyz", response_model=ReadinessResponse)
def readyz():
    """Readiness probe — checks if Playwright Chromium binary is available."""
    pw_ok = _playwright_available()
    checks = {
        "playwright_package": "ready" if pw_ok else "unavailable — run: playwright install chromium",
        "headless_engine": "chromium",
        "screenshots_dir": SCREENSHOTS_DIR
    }
    if not pw_ok:
        return JSONResponse(
            status_code=503,
            content=ReadinessResponse(
                status="not_ready", service="browser-service", checks=checks
            ).model_dump()
        )
    return ReadinessResponse(status="ready", service="browser-service", checks=checks)


# ---------------------------------------------------------------------------
# Search endpoint
# ---------------------------------------------------------------------------

@app.post("/api/v1/search", response_model=BrowserSearchResponse)
async def search(request: BrowserSearchRequest):
    """
    Searches Google for `request.query` and returns up to `max_results` results.
    Each result contains title, URL, and an optional snippet.
    """
    logger.info(f"[Browser] /search — query='{request.query}' max={request.max_results}")
    try:
        results = await asyncio.wait_for(
            _do_search(request.query, request.max_results),
            timeout=BROWSER_TIMEOUT_MS / 1000 + 5
        )
        return BrowserSearchResponse(
            query=request.query,
            results=results,
            success=True
        )
    except asyncio.TimeoutError:
        logger.error(f"[Browser] Search timed out for query: '{request.query}'")
        return BrowserSearchResponse(
            query=request.query,
            results=[],
            success=False,
            error=f"Search timed out after {BROWSER_TIMEOUT_MS / 1000:.0f}s"
        )
    except Exception as e:
        logger.error(f"[Browser] Search error: {e}")
        return BrowserSearchResponse(
            query=request.query,
            results=[],
            success=False,
            error=str(e)
        )


# ---------------------------------------------------------------------------
# Browse/navigate endpoint
# ---------------------------------------------------------------------------

@app.post("/api/v1/browse", response_model=BrowserActionResponse)
async def browse(request: BrowserActionRequest):
    """
    Executes a browser automation command.

    Actions:
      - "search"     → search Google for request.query, return top results
      - "navigate"   → navigate to request.url, return page title + text
      - "screenshot" → capture screenshot of request.url (optional), return path
    """
    logger.info(f"[Browser] /browse — action='{request.action}' url={request.url} query={request.query}")

    # --- search ---
    if request.action == "search":
        query = request.query or request.url or ""
        if not query:
            return BrowserActionResponse(
                success=False,
                error="'search' action requires a 'query' field."
            )
        try:
            results = await asyncio.wait_for(
                _do_search(query, request.max_results),
                timeout=BROWSER_TIMEOUT_MS / 1000 + 5
            )
            return BrowserActionResponse(
                success=True,
                extracted_text=f"Found {len(results)} results for '{query}'",
                search_results=results
            )
        except asyncio.TimeoutError:
            return BrowserActionResponse(
                success=False,
                error=f"Search timed out after {BROWSER_TIMEOUT_MS / 1000:.0f}s"
            )
        except Exception as e:
            return BrowserActionResponse(success=False, error=str(e))

    # --- navigate ---
    elif request.action in ("navigate", "browse"):
        if not request.url:
            return BrowserActionResponse(
                success=False,
                error=f"'{request.action}' action requires a 'url' field."
            )
        try:
            title, text, _ = await asyncio.wait_for(
                _do_navigate(request.url),
                timeout=BROWSER_TIMEOUT_MS / 1000 + 5
            )
            return BrowserActionResponse(
                success=True,
                page_title=title,
                extracted_text=text
            )
        except asyncio.TimeoutError:
            return BrowserActionResponse(
                success=False,
                error=f"Navigation timed out after {BROWSER_TIMEOUT_MS / 1000:.0f}s"
            )
        except Exception as e:
            return BrowserActionResponse(success=False, error=str(e))

    # --- screenshot ---
    elif request.action == "screenshot":
        try:
            filepath = await asyncio.wait_for(
                _do_screenshot(request.url),
                timeout=BROWSER_TIMEOUT_MS / 1000 + 5
            )
            return BrowserActionResponse(
                success=True,
                screenshot_path=filepath,
                extracted_text=f"Screenshot saved to {filepath}"
            )
        except asyncio.TimeoutError:
            return BrowserActionResponse(
                success=False,
                error="Screenshot timed out"
            )
        except Exception as e:
            return BrowserActionResponse(success=False, error=str(e))

    else:
        return BrowserActionResponse(
            success=False,
            error=f"Unsupported action '{request.action}'. Supported: search, navigate, screenshot."
        )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8003))
    logger.info(f"Starting JARVIS Browser Service v2 on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
