"""codewiki_request_indexing tool — Submit a repo to CodeWiki for indexing.

When a repository is not yet indexed by Google CodeWiki, this tool:
1. Searches for the repo on CodeWiki's homepage.
2. Clicks "Request repository" if the repo is not found.
3. Fills in the repo URL in the dialog and submits.
4. Returns a confirmation message with next-step guidance.

Uses Playwright (via the shared browser loop) to interact with the
CodeWiki Angular SPA, following the same patterns as codewiki_search_wiki.
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse

from mcp.server.fastmcp import FastMCP

from .. import config
from ..browser import _get_browser, run_in_browser_loop
from ..stealth import apply_stealth_scripts, random_delay, stealth_context_options
from ..types import (
    ErrorCode,
    ResponseMeta,
    ResponseStatus,
    ToolResponse,
    validate_topics_input,
)
from ._helpers import build_codewiki_url, build_resolution_note

logger = logging.getLogger("CodeWiki")

# ---------------------------------------------------------------------------
# Selectors for the request-repo flow
# ---------------------------------------------------------------------------
SEARCH_INPUT_SELECTOR = "input[type='text'], input[type='search'], textbox"
REQUEST_REPO_BUTTON = "button:has-text('Request repository')"
DIALOG_URL_INPUT = "dialog input, dialog textbox"
DIALOG_SUBMIT_BUTTON = "dialog button:has-text('Submit')"
CONFIRMATION_HEADING = "h3:has-text('Repo requested')"


# ---------------------------------------------------------------------------
# Async implementation
# ---------------------------------------------------------------------------
async def _request_indexing_impl(repo_url: str) -> ToolResponse:
    """Submit a repo-indexing request on CodeWiki via Playwright.

    Flow:
        1. Navigate to codewiki.google/search?q=owner/repo
        2. Wait for "Request repository" button
        3. Click it → dialog opens
        4. Fill the GitHub URL → click Submit
        5. Wait for confirmation toast/heading
    """
    # Extract owner/repo from the full URL for the search query
    clean = repo_url.replace("https://github.com/", "").replace("http://github.com/", "")
    search_url = (
        f"{config.CODEWIKI_BASE_URL}/search"
        f"?q={urllib.parse.quote(clean, safe='')}"
    )

    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    try:
        # Step 1: Navigate to search results
        logger.info("codewiki_request_indexing: navigating to %s", search_url)
        await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
        )
        await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        # Step 2: Look for "Request repository" button
        try:
            req_btn = page.get_by_role("button", name="Request repository")
            await req_btn.wait_for(state="visible", timeout=10_000)
        except Exception:
            # The repo might already be indexed, or page layout changed
            return ToolResponse(
                status=ResponseStatus.OK,
                code=ErrorCode.NOT_INDEXED,
                data=(
                    f"Could not find the 'Request repository' button for "
                    f"**{repo_url}**. The repo may already be queued for "
                    f"indexing, or CodeWiki's UI has changed.\n\n"
                    f"You can try manually at: {search_url}"
                ),
                repo_url=repo_url,
            )

        # Step 3: Click "Request repository" → dialog opens
        await random_delay(0.3, 0.8)
        await req_btn.click()
        logger.debug("Clicked 'Request repository'")
        await random_delay(0.5, 1.0)

        # Step 4: Fill the URL in the dialog
        try:
            url_input = page.get_by_role("textbox", name="Enter URL")
            await url_input.wait_for(state="visible", timeout=5_000)
        except Exception:
            # Try broader selectors
            try:
                url_input = page.locator("dialog textbox, dialog input").first
                await url_input.wait_for(state="visible", timeout=3_000)
            except Exception:
                return ToolResponse(
                    status=ResponseStatus.OK,
                    code=ErrorCode.NOT_INDEXED,
                    data=(
                        f"The request dialog opened but the URL input field "
                        f"was not found for **{repo_url}**.\n\n"
                        f"Please submit manually at: {search_url}"
                    ),
                    repo_url=repo_url,
                )

        await url_input.fill(repo_url)
        await random_delay(0.3, 0.6)

        # Step 5: Click Submit
        try:
            submit_btn = page.get_by_role("button", name="Submit")
            await submit_btn.wait_for(state="visible", timeout=3_000)
            # Wait until enabled (it's disabled until URL is entered)
            for _ in range(10):
                if not await submit_btn.is_disabled():
                    break
                await asyncio.sleep(0.3)
            await submit_btn.click()
            logger.debug("Clicked 'Submit' in request dialog")
        except Exception as exc:
            return ToolResponse(
                status=ResponseStatus.OK,
                code=ErrorCode.NOT_INDEXED,
                data=(
                    f"Filled URL but could not click Submit for **{repo_url}**: "
                    f"{exc}\n\nPlease submit manually at: {search_url}"
                ),
                repo_url=repo_url,
            )

        # Step 6: Wait for confirmation
        await asyncio.sleep(2)
        confirmed = False
        try:
            heading = page.get_by_role("heading", name="Repo requested")
            if await heading.is_visible(timeout=5_000):
                confirmed = True
        except Exception:
            pass

        if not confirmed:
            # Check the page text as fallback
            try:
                body_text = await page.inner_text("body")
                if "repo requested" in body_text.lower() or "we'll review" in body_text.lower():
                    confirmed = True
            except Exception:
                pass

        codewiki_url = build_codewiki_url(repo_url)
        if confirmed:
            message = (
                f"**Indexing request submitted successfully** for "
                f"**{repo_url}**.\n\n"
                f"Google CodeWiki confirmed: *\"Repo requested — Thanks for "
                f"reaching out. We'll review your request.\"*\n\n"
                f"**What to do next:**\n"
                f"- The wiki will be generated once Google reviews and "
                f"approves the request.\n"
                f"- Check back later at: {codewiki_url}\n"
                f"- Indexing timelines vary — popular repos with more stars "
                f"and activity are typically indexed sooner.\n"
                f"- Try querying this repo again in a few days."
            )
        else:
            message = (
                f"The indexing request was submitted for **{repo_url}**, "
                f"but we could not confirm whether it was accepted.\n\n"
                f"**What to do next:**\n"
                f"- Check: {codewiki_url}\n"
                f"- Or submit manually at: {search_url}\n"
                f"- Try again in a few days."
            )

        return ToolResponse(
            status=ResponseStatus.OK,
            code=ErrorCode.NOT_INDEXED,
            data=message,
            repo_url=repo_url,
            meta=ResponseMeta(char_count=len(message)),
        )

    except Exception as exc:
        logger.error("codewiki_request_indexing failed: %s", exc)
        return ToolResponse.error(
            ErrorCode.DRIVER_ERROR,
            f"Playwright error during indexing request: {exc}",
            repo_url=repo_url,
        )
    finally:
        await page.close()
        await context.close()


# ---------------------------------------------------------------------------
# Sync wrapper
# ---------------------------------------------------------------------------
def _run_request_indexing(repo_url: str) -> ToolResponse:
    """Run the async request in the persistent Playwright event loop."""
    try:
        return run_in_browser_loop(_request_indexing_impl(repo_url))
    except asyncio.TimeoutError:
        return ToolResponse.error(
            ErrorCode.TIMEOUT,
            f"Request timed out after {config.HARD_TIMEOUT_SECONDS}s.",
            repo_url=repo_url,
        )
    except Exception as exc:
        return ToolResponse.error(
            ErrorCode.INTERNAL,
            str(exc),
            repo_url=repo_url,
        )


# ---------------------------------------------------------------------------
# Public: tool registration
# ---------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the codewiki_request_indexing tool on the MCP server."""

    @mcp.tool()
    def codewiki_request_indexing(repo_url: str) -> str:
        """
        Request Google CodeWiki to index a repository that is not yet available.

        Use this tool when ``codewiki_list_topics`` or ``codewiki_read_structure``
        returns a ``NOT_INDEXED`` error, indicating the repository has no
        CodeWiki documentation yet.

        This tool will:
        1. Search for the repository on CodeWiki.
        2. Click "Request repository" to open the submission dialog.
        3. Fill in the GitHub URL and submit the request.
        4. Return confirmation and next-step guidance.

        **Note**: Google CodeWiki reviews requests and indexes repositories
        based on popularity and demand.  There is no guaranteed timeline.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/owner/repo)
                      or shorthand owner/repo (e.g. owner/repo).
        """
        start = time.monotonic()
        logger.info("codewiki_request_indexing — repo: %s", repo_url)

        original_input = repo_url  # save before validation resolves keywords

        validated = validate_topics_input(repo_url)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        note = build_resolution_note(original_input, validated.repo_url)
        result = _run_request_indexing(validated.repo_url)
        result.meta.elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.data and note:
            result.data = note + result.data
        return result.to_text()
