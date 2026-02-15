"""Shared helpers for CodeWiki MCP tools.

Eliminates boilerplate duplicated across tool modules: input validation,
page fetching with error handling, response truncation, URL construction,
in-flight deduplication, and rate limiting.
"""

from __future__ import annotations

import logging

from .. import config
from ..dedup import dedup_fetch
from ..parser import WikiPage, fetch_wiki_page
from ..rate_limit import check_rate_limit
from ..types import (
    ErrorCode,
    ToolResponse,
    validate_topics_input,
)

logger = logging.getLogger("CodeWiki")


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------
def build_codewiki_url(repo_url: str) -> str:
    """Convert a normalised repo URL to a full CodeWiki page URL.

    Example::

        >>> build_codewiki_url("https://github.com/microsoft/vscode")
        'https://codewiki.google/github.com/microsoft/vscode'
    """
    clean = repo_url.replace("https://", "").replace("http://", "")
    return f"{config.CODEWIKI_BASE_URL}/{clean}"


# ---------------------------------------------------------------------------
# Truncation with word-boundary awareness
# ---------------------------------------------------------------------------
def truncate_response(data: str, max_chars: int = 0) -> tuple[str, bool]:
    """Truncate *data* at a word boundary near *max_chars*.

    Returns ``(text, was_truncated)``.  If *max_chars* is 0 or the text
    is shorter, returns the original text unchanged.
    """
    if not max_chars or len(data) <= max_chars:
        return data, False

    # Try to break at the last newline before the limit
    cut = data[:max_chars]
    last_nl = cut.rfind("\n")
    if last_nl > max_chars * 0.8:  # only if we keep ≥80% of the budget
        cut = cut[:last_nl]
    else:
        # Fall back to last space
        last_sp = cut.rfind(" ")
        if last_sp > max_chars * 0.8:
            cut = cut[:last_sp]

    return cut.rstrip() + "\n\n... [truncated]", True


# ---------------------------------------------------------------------------
# Unified page fetcher with error handling
# ---------------------------------------------------------------------------
def fetch_page_or_error(repo_url: str) -> WikiPage | ToolResponse:
    """Validate *repo_url*, fetch and return a WikiPage, or a ToolResponse error.

    Handles validation, rate limiting, in-flight deduplication, NO_CONTENT,
    TIMEOUT, and generic exceptions in one place so tool modules don't have
    to duplicate the same try/except block.
    """
    validated = validate_topics_input(repo_url)
    if isinstance(validated, ToolResponse):
        return validated

    # --- Rate limiting ---
    if not check_rate_limit(validated.repo_url):
        return ToolResponse.error(
            ErrorCode.RATE_LIMITED,
            f"Rate limit exceeded for {validated.repo_url}. "
            f"Max {config.RATE_LIMIT_MAX_CALLS} calls per "
            f"{config.RATE_LIMIT_WINDOW_SECONDS}s window. "
            "Please wait before retrying.",
            repo_url=validated.repo_url,
        )

    # --- Deduplicated fetch ---
    try:
        page = dedup_fetch(
            validated.repo_url,
            lambda: fetch_wiki_page(validated.repo_url),
        )
    except TimeoutError as exc:
        return ToolResponse.error(
            ErrorCode.TIMEOUT,
            f"Timed out fetching CodeWiki page for {validated.repo_url}: {exc}",
            repo_url=validated.repo_url,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return ToolResponse.error(
            ErrorCode.INTERNAL,
            f"Failed to fetch CodeWiki page: {exc}",
            repo_url=validated.repo_url,
        )

    if not page.sections and not page.raw_text:
        return ToolResponse.error(
            ErrorCode.NO_CONTENT,
            f"No content found for {validated.repo_url}. "
            "The repository may not be indexed by CodeWiki.",
            repo_url=validated.repo_url,
        )

    return page
