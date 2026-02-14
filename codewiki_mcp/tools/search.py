"""search_code_wiki tool — Ask Google CodeWiki a question via Playwright chat.

The chat feature on CodeWiki is an Angular SPA with a ``<chat>`` custom element
containing ``<new-message-form>`` (textarea + send button) and ``<thread>``
(virtual-scroll message list).  All interaction requires Playwright.
"""

from __future__ import annotations

import asyncio
import logging
import time

from mcp.server.fastmcp import FastMCP

from .. import config
from ..browser import _get_browser, cleanup_browser, run_in_browser_loop
from ..types import (
    ErrorCode,
    ResponseMeta,
    SearchInput,
    ToolResponse,
    validate_search_input,
)

logger = logging.getLogger("CodeWiki")


# ---------------------------------------------------------------------------
# Chat interaction helpers
# ---------------------------------------------------------------------------
async def _ensure_chat_open(page) -> bool:
    """Make sure the chat panel is open.  Returns True if visible."""
    # Already open?
    try:
        chat = page.locator(config.CHAT_OPEN_SELECTOR)
        if await chat.is_visible(timeout=2000):
            logger.debug("Chat panel already open")
            return True
    except Exception:
        pass

    # Try clicking the toggle button
    try:
        toggle = page.locator(config.CHAT_TOGGLE_SELECTOR).first
        if await toggle.is_visible(timeout=2000):
            await toggle.click()
            logger.debug("Clicked chat toggle")
            await asyncio.sleep(1)
            chat = page.locator(config.CHAT_OPEN_SELECTOR)
            if await chat.is_visible(timeout=3000):
                return True
    except Exception:
        pass

    return False


async def _find_chat_input(page):
    """Find the chat input textarea."""
    for selector in config.CHAT_INPUT_SELECTORS:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=2000):
                logger.debug("Found chat input: %s", selector)
                return elem
        except Exception:
            continue
    return None


async def _wait_for_submit_enabled(page, timeout_ms: int = 5000) -> None:
    """Wait for the send button to become enabled after typing."""
    for selector in config.SUBMIT_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=1000):
                await btn.wait_for(state="attached", timeout=timeout_ms)
                # Poll until not disabled
                deadline = time.monotonic() + timeout_ms / 1000
                while time.monotonic() < deadline:
                    disabled = await btn.is_disabled()
                    if not disabled:
                        return
                    await asyncio.sleep(0.2)
        except Exception:
            continue


async def _click_submit(page) -> bool:
    """Click the submit/send button.  Returns True if clicked."""
    for selector in config.SUBMIT_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=1000):
                disabled = await btn.is_disabled()
                if not disabled:
                    await btn.click()
                    logger.debug("Clicked submit: %s", selector)
                    return True
        except Exception:
            continue
    return False


async def _wait_for_response(page) -> str:
    """Wait for the chat response to appear and stabilize in the thread.

    CodeWiki renders responses inside ``<thread>`` → virtual-scroll →
    ``<documentation-markdown>``.  When the chat is empty, a
    ``.empty-house-container`` is shown — we wait for it to disappear and
    real message content to appear.
    """
    deadline = time.monotonic() + config.RESPONSE_WAIT_TIMEOUT_SECONDS

    # Phase 1: wait for the empty-house to go away (means a message appeared)
    logger.debug("Waiting for empty-house to disappear…")
    while time.monotonic() < deadline:
        try:
            empty = page.locator(config.CHAT_EMPTY_STATE_SELECTOR)
            if not await empty.is_visible(timeout=500):
                break
        except Exception:
            break
        await asyncio.sleep(1)

    # Phase 2: wait for content inside the scroll wrapper
    logger.debug("Waiting for response content in thread…")
    content = ""
    while time.monotonic() < deadline:
        await asyncio.sleep(config.RESPONSE_POLL_INTERVAL_SECONDS)
        for sel in config.RESPONSE_ELEMENT_SELECTORS:
            try:
                elem = page.locator(sel).last  # last = latest message
                if await elem.is_visible(timeout=500):
                    text = await elem.inner_text()
                    if len(text) > config.NEW_CONTENT_THRESHOLD_CHARS:
                        content = text
                        break
            except Exception:
                continue
        if content:
            break

    if not content:
        return ""

    # Phase 3: wait for streaming to stabilize
    last_len = len(content)
    for _ in range(15):
        await asyncio.sleep(config.RESPONSE_STABLE_INTERVAL_SECONDS)
        for sel in config.RESPONSE_ELEMENT_SELECTORS:
            try:
                elem = page.locator(sel).last
                if await elem.is_visible(timeout=500):
                    content = await elem.inner_text()
                    break
            except Exception:
                continue
        if len(content) == last_len:
            logger.debug("Response stabilized at %d chars", last_len)
            break
        last_len = len(content)

    return content


def _clean_response(raw: str) -> str:
    """Strip UI artifacts like icon text from the response."""
    for artifact in config.UI_ARTIFACTS:
        raw = raw.replace(artifact, "")

    # Remove leading/trailing whitespace on each line, collapse blank lines
    lines = [line.strip() for line in raw.split("\n")]
    # Remove empty leading lines
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines).strip()


async def _search_impl(inp: SearchInput) -> ToolResponse:
    """One Playwright-based attempt at querying CodeWiki chat."""
    clean_repo = inp.repo_url.replace("https://", "").replace("http://", "")
    target_url = f"{config.CODEWIKI_BASE_URL}/{clean_repo}"
    logger.info("Target URL: %s", target_url)

    browser = await _get_browser()
    context = await browser.new_context(
        user_agent=config.USER_AGENT,
        viewport={"width": 1920, "height": 1080},
    )
    page = await context.new_page()

    try:
        await page.goto(target_url, wait_until="domcontentloaded",
                        timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000)

        # Wait for the SPA to render the wiki page
        try:
            await page.wait_for_selector(
                "body-content-section, documentation-markdown, h1",
                timeout=config.ELEMENT_WAIT_TIMEOUT_SECONDS * 1000,
            )
        except Exception:
            pass
        await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        # Ensure the chat panel is open
        chat_visible = await _ensure_chat_open(page)
        if not chat_visible:
            return ToolResponse.error(
                ErrorCode.INPUT_NOT_FOUND,
                f"Chat panel not found or could not be opened on {target_url}.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        # Find the chat input
        chat_input = await _find_chat_input(page)
        if not chat_input:
            return ToolResponse.error(
                ErrorCode.INPUT_NOT_FOUND,
                f"Could not locate chat input on {target_url}. "
                "CodeWiki may require authentication or the page structure has changed.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        # Type the query
        await chat_input.click()
        await chat_input.fill("")
        await asyncio.sleep(config.INPUT_CLEAR_DELAY)
        await chat_input.fill(inp.query)
        await asyncio.sleep(config.INPUT_TYPE_DELAY)

        # Wait for the send button to become enabled (it starts disabled)
        await _wait_for_submit_enabled(page, timeout_ms=3000)

        # Submit via Enter key first, then click button as fallback
        await chat_input.press("Enter")
        await asyncio.sleep(0.5)
        await _click_submit(page)

        # Wait a bit before polling for response
        await asyncio.sleep(config.RESPONSE_INITIAL_DELAY_SECONDS)

        # Wait for response
        response_text = await _wait_for_response(page)

        if not response_text:
            return ToolResponse.error(
                ErrorCode.NO_CONTENT,
                f"No response received for query: '{inp.query}'.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        cleaned = _clean_response(response_text)
        truncated = False
        if len(cleaned) > config.RESPONSE_MAX_CHARS:
            cleaned = cleaned[: config.RESPONSE_MAX_CHARS] + "\n\n... [truncated]"
            truncated = True

        return ToolResponse.success(
            cleaned,
            repo_url=inp.repo_url,
            query=inp.query,
            meta=ResponseMeta(char_count=len(cleaned), truncated=truncated),
        )

    except Exception as exc:
        return ToolResponse.error(
            ErrorCode.DRIVER_ERROR,
            f"Playwright error: {exc}",
            repo_url=inp.repo_url,
            query=inp.query,
        )
    finally:
        await page.close()
        await context.close()


# ---------------------------------------------------------------------------
# Sync wrapper for the async search
# ---------------------------------------------------------------------------
def _run_search(inp: SearchInput) -> ToolResponse:
    """Run the async search in the persistent Playwright event loop."""
    try:
        return run_in_browser_loop(_search_impl(inp))
    except asyncio.TimeoutError:
        return ToolResponse.error(
            ErrorCode.TIMEOUT,
            f"Search timed out after {config.HARD_TIMEOUT_SECONDS}s.",
            repo_url=inp.repo_url,
            query=inp.query,
        )
    except Exception as exc:
        return ToolResponse.error(
            ErrorCode.INTERNAL,
            str(exc),
            repo_url=inp.repo_url,
            query=inp.query,
        )


# ---------------------------------------------------------------------------
# Public: tool registration
# ---------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the search_code_wiki tool on the MCP server."""

    @mcp.tool()
    def search_code_wiki(repo_url: str, query: str = "") -> str:
        """
        Ask Google CodeWiki a question about an open-source repository.

        This uses the interactive chat feature powered by Gemini.
        For reading wiki content directly, use ``read_wiki_contents`` instead.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/microsoft/vscode-copilot-chat)
                      or shorthand owner/repo (e.g. microsoft/vscode-copilot-chat).
            query: The question to ask (required).
        """
        start = time.monotonic()
        logger.info("search_code_wiki — repo: %s, query: %s", repo_url, query)

        validated = validate_search_input(repo_url, query)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        last_error: ToolResponse | None = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            logger.info("Attempt %d/%d", attempt, config.MAX_RETRIES)

            result = _run_search(validated)

            if result.status.value == "ok":
                result.meta.attempt = attempt
                result.meta.max_attempts = config.MAX_RETRIES
                result.meta.elapsed_ms = int((time.monotonic() - start) * 1000)
                return result.to_text()

            last_error = result
            last_error.meta.attempt = attempt
            last_error.meta.max_attempts = config.MAX_RETRIES

            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_DELAY_SECONDS)

        if last_error:
            last_error.code = ErrorCode.RETRY_EXHAUSTED
            last_error.meta.elapsed_ms = int((time.monotonic() - start) * 1000)
            return last_error.to_text()

        return ToolResponse.error(ErrorCode.INTERNAL, "All retry attempts failed.").to_text()
