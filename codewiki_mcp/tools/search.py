"""codewiki_search_wiki tool — Ask Google CodeWiki a question via Playwright chat.

The chat feature on CodeWiki is an Angular SPA with a ``<chat>`` custom element
containing ``<new-message-form>`` (textarea + send button) and ``<thread>``
(virtual-scroll message list).  All interaction requires Playwright.
"""

from __future__ import annotations

import asyncio
import logging
import time

from mcp.server.fastmcp import Context, FastMCP

from .. import config
from ..browser import _get_browser, run_in_browser_loop
from ..cache import get_cached_search, set_cached_search
from ..rate_limit import check_rate_limit
from ..session_pool import (
    _get_or_create,
    _release,
)
from ..stealth import (
    apply_stealth_scripts,
    human_click,
    human_type,
    random_delay,
    stealth_context_options,
)
from ..types import (
    ErrorCode,
    ResponseMeta,
    SearchInput,
    ToolResponse,
    validate_search_input,
)
from ._helpers import build_codewiki_url, build_resolution_note, pre_resolve_keyword

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
        logger.debug("Suppressed exception during cleanup", exc_info=True)

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
        logger.debug("Suppressed exception during cleanup", exc_info=True)

    return False


async def _find_chat_input(page):
    """Find the chat input textarea."""
    for selector in config.CHAT_INPUT_SELECTORS:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=2000):
                logger.debug("Found chat input: %s", selector)
                return elem
        except Exception:  # pylint: disable=broad-except
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
        except Exception:  # pylint: disable=broad-except
            continue


async def _submit_query(page, chat_input) -> None:
    """Submit the chat query via Enter; fall back to button click if needed.

    After pressing Enter, the send button becomes disabled if the message
    was accepted.  Only click the button when Enter did NOT submit.
    """
    await chat_input.press("Enter")
    await random_delay(0.3, 0.6)

    # Check if Enter already submitted (button disabled = message sent)
    for selector in config.SUBMIT_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=1000):
                if await btn.is_disabled():
                    logger.debug("Enter submitted successfully (button disabled)")
                    return
                # Button still enabled → Enter didn't work, click it
                await btn.click()
                logger.debug("Clicked submit as fallback: %s", selector)
                return
        except Exception:  # pylint: disable=broad-except
            continue
    logger.debug("No submit button found after Enter")


async def _wait_for_response(page) -> str:  # pylint: disable=too-many-branches
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
        except Exception:  # pylint: disable=broad-except
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
            except Exception:  # pylint: disable=broad-except
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
            except Exception:  # pylint: disable=broad-except
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
    """One Playwright-based attempt at querying CodeWiki chat.

    Uses the session pool to reuse warm browser contexts when possible.
    Falls back to a fresh context if the pooled session is broken.
    """
    target_url = build_codewiki_url(inp.repo_url)
    logger.info("Target URL: %s", target_url)

    # Try to get a warm session from the pool
    # NOTE: _search_impl runs ON the browser event loop, so we must use the
    # async _get_or_create/_release directly — the sync wrappers would
    # deadlock by trying to submit coroutines to this same loop.
    broken = False
    try:
        entry = await _get_or_create(target_url)
        page = entry.page
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Session pool failed, falling back to fresh context: %s", exc)
        return await _search_fresh_context(inp, target_url)

    try:
        # Ensure the chat panel is open
        chat_visible = await _ensure_chat_open_async(page)
        if not chat_visible:
            broken = True
            return ToolResponse.error(
                ErrorCode.INPUT_NOT_FOUND,
                f"Chat panel not found or could not be opened on {target_url}.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        # Find the chat input
        chat_input = await _find_chat_input(page)
        if not chat_input:
            broken = True
            return ToolResponse.error(
                ErrorCode.INPUT_NOT_FOUND,
                f"Could not locate chat input on {target_url}. "
                "CodeWiki may require authentication or the page structure has changed.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        # Type the query (human-like: char-by-char with jitter)
        await human_click(page, chat_input)
        await random_delay(0.2, 0.5)
        await chat_input.fill("")  # clear first
        await random_delay(0.2, 0.4)
        await human_type(chat_input, inp.query)
        await random_delay(0.3, 0.8)

        # Wait for the send button to become enabled
        await _wait_for_submit_enabled(page, timeout_ms=3000)

        # Submit the query
        await random_delay(0.1, 0.3)
        await _submit_query(page, chat_input)

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

    except Exception as exc:  # pylint: disable=broad-except
        broken = True
        return ToolResponse.error(
            ErrorCode.DRIVER_ERROR,
            f"Playwright error: {exc}",
            repo_url=inp.repo_url,
            query=inp.query,
        )
    finally:
        await _release(target_url, broken=broken)


async def _ensure_chat_open_async(page) -> bool:
    """Wrapper that uses the module-level _ensure_chat_open."""
    return await _ensure_chat_open(page)


async def _search_fresh_context(inp: SearchInput, target_url: str) -> ToolResponse:
    """Fallback: create a one-off browser context (pre-v1.0.2 behaviour)."""
    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    try:
        await page.goto(
            target_url,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
        )
        try:
            await page.wait_for_selector(
                "body-content-section, documentation-markdown, h1",
                timeout=config.ELEMENT_WAIT_TIMEOUT_SECONDS * 1000,
            )
        except Exception:
            logger.debug("Suppressed exception during cleanup", exc_info=True)
        await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        chat_visible = await _ensure_chat_open(page)
        if not chat_visible:
            return ToolResponse.error(
                ErrorCode.INPUT_NOT_FOUND,
                f"Chat panel not found on {target_url}.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        chat_input = await _find_chat_input(page)
        if not chat_input:
            return ToolResponse.error(
                ErrorCode.INPUT_NOT_FOUND,
                f"Could not locate chat input on {target_url}.",
                repo_url=inp.repo_url,
                query=inp.query,
            )

        await human_click(page, chat_input)
        await random_delay(0.2, 0.5)
        await chat_input.fill("")
        await random_delay(0.2, 0.4)
        await human_type(chat_input, inp.query)
        await random_delay(0.3, 0.8)
        await _wait_for_submit_enabled(page, timeout_ms=3000)
        await random_delay(0.1, 0.3)
        await _submit_query(page, chat_input)
        await asyncio.sleep(config.RESPONSE_INITIAL_DELAY_SECONDS)

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

    except Exception as exc:  # pylint: disable=broad-except
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
    except Exception as exc:  # pylint: disable=broad-except
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
    """Register the codewiki_search_wiki tool on the MCP server."""

    @mcp.tool()
    def codewiki_search_wiki(repo_url: str, query: str = "", ctx: Context | None = None) -> str:
        """
        Ask Google CodeWiki a question about an open-source repository.

        This uses the interactive chat feature powered by Gemini.
        For reading wiki content directly, use ``codewiki_read_contents`` instead.

        Results are cached for 2 minutes — repeated identical queries are instant.

        **Response size**: typically 0.5–5 KB depending on the answer.

        **Rate limit**: max 10 calls per 60 s per repo URL.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/microsoft/vscode-copilot-chat)
                      or shorthand owner/repo (e.g. microsoft/vscode-copilot-chat).
                      Bare keywords (e.g. 'vue') are auto-resolved with
                      interactive disambiguation.
            query: The question to ask (required).
        """
        start = time.monotonic()
        logger.info("codewiki_search_wiki — repo: %s, query: %s", repo_url, query)

        original_input = repo_url  # save before resolution
        repo_url = pre_resolve_keyword(repo_url, ctx)  # elicitation for bare keywords

        validated = validate_search_input(repo_url, query)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        # --- Rate limiting ---
        if not check_rate_limit(validated.repo_url):
            return ToolResponse.error(
                ErrorCode.RATE_LIMITED,
                f"Rate limit exceeded for {validated.repo_url}. "
                f"Max {config.RATE_LIMIT_MAX_CALLS} calls per "
                f"{config.RATE_LIMIT_WINDOW_SECONDS}s window. "
                "Please wait before retrying.",
                repo_url=validated.repo_url,
                query=validated.query,
            ).to_text()

        note = build_resolution_note(original_input, validated.repo_url)

        # Check search cache first
        cached = get_cached_search(validated.repo_url, validated.query)
        if cached is not None:
            elapsed = int((time.monotonic() - start) * 1000)
            return ToolResponse.success(
                note + cached,
                repo_url=validated.repo_url,
                query=validated.query,
                meta=ResponseMeta(
                    elapsed_ms=elapsed,
                    char_count=len(cached),
                ),
            ).to_text()

        last_error: ToolResponse | None = None
        for attempt in range(1, config.MAX_RETRIES + 1):
            logger.info("Attempt %d/%d", attempt, config.MAX_RETRIES)

            result = _run_search(validated)

            if result.status.value == "ok":
                result.meta.attempt = attempt
                result.meta.max_attempts = config.MAX_RETRIES
                result.meta.elapsed_ms = int((time.monotonic() - start) * 1000)
                # Cache the successful result
                if result.data:
                    set_cached_search(validated.repo_url, validated.query, result.data)
                    result.data = note + result.data
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

        return ToolResponse.error(
            ErrorCode.INTERNAL, "All retry attempts failed."
        ).to_text()
