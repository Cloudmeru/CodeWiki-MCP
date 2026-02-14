"""Shared Playwright browser singleton for CodeWiki MCP.

CodeWiki is a JavaScript SPA (Angular), so all page content requires
browser rendering. This module provides a shared, lazily-initialized
Playwright Chromium instance used by both the wiki parser and the chat tool.

**Architecture**: A single persistent event loop runs in a daemon thread.
All Playwright operations are submitted to this loop via
``run_in_browser_loop()``, ensuring the async browser singleton never
crosses event-loop boundaries.
"""

from __future__ import annotations

import asyncio
import logging
import threading

from . import config

logger = logging.getLogger("CodeWiki")

# ---------------------------------------------------------------------------
# Persistent background event loop (single-threaded)
# ---------------------------------------------------------------------------
_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()

# Playwright state — only touched from _loop
_browser = None
_pw = None


def _start_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Target for the daemon thread — runs *loop* forever."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent background event loop, creating it on first call."""
    global _loop, _thread
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            _thread = threading.Thread(
                target=_start_loop, args=(_loop,), daemon=True, name="pw-loop",
            )
            _thread.start()
    return _loop


def run_in_browser_loop(coro):
    """Submit *coro* to the persistent Playwright loop and block for result.

    This is the **only** correct way to call Playwright from synchronous
    MCP tool handlers. Never use ``asyncio.run()`` — that would create a
    new event loop and invalidate the browser singleton.
    """
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=config.HARD_TIMEOUT_SECONDS)


# ---------------------------------------------------------------------------
# Browser singleton (runs inside _loop)
# ---------------------------------------------------------------------------
async def _get_browser():
    """Lazily launch a shared Playwright Chromium browser instance."""
    global _browser, _pw
    if _browser is None or not _browser.is_connected():
        from playwright.async_api import async_playwright

        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
            ],
        )
        logger.debug("Playwright browser launched")
    return _browser


async def cleanup_browser():
    """Close the shared browser instance."""
    global _browser, _pw
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
        _pw = None
    logger.debug("Playwright browser cleaned up")


# ---------------------------------------------------------------------------
# Render a page (navigate + wait for JS)
# ---------------------------------------------------------------------------
async def _render_page_async(url: str) -> str:
    """Navigate to *url* with Playwright and return the rendered HTML."""
    browser = await _get_browser()
    context = await browser.new_context(
        user_agent=config.USER_AGENT,
        viewport={"width": 1920, "height": 1080},
    )
    page = await context.new_page()
    try:
        logger.info("Rendering %s via Playwright...", url)
        await page.goto(url, wait_until="domcontentloaded",
                        timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000)
        # Wait for the Angular SPA to render content
        # Try to wait for meaningful content to appear
        try:
            await page.wait_for_selector(
                "h1, h2, h3, article, main, [class*='content']",
                timeout=config.ELEMENT_WAIT_TIMEOUT_SECONDS * 1000,
            )
        except Exception:
            # Fallback: just wait a fixed time for JS to execute
            await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        # Extra settle time for dynamic content
        await asyncio.sleep(1)

        html = await page.content()
        logger.debug("Rendered %s — %d chars HTML", url, len(html))
        return html
    finally:
        await page.close()
        await context.close()


def fetch_rendered_html(url: str) -> str:
    """Synchronous wrapper: render a page with Playwright and return HTML.

    Safe to call from sync MCP tool handlers — submits work to the
    persistent Playwright event loop.
    """
    return run_in_browser_loop(_render_page_async(url))
