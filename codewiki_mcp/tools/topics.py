"""list_code_wiki_topics tool — Lightweight topic discovery.

Returns section titles with short content previews — dramatically more
token-efficient than dumping the full page.  For full content, use
``read_wiki_contents`` with pagination.
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import FastMCP

from .. import config
from ..parser import page_to_topic_list
from ..types import ResponseMeta, ToolResponse
from ._helpers import fetch_page_or_error, truncate_response

logger = logging.getLogger("CodeWiki")


# ---------------------------------------------------------------------------
# Public: tool registration
# ---------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the list_code_wiki_topics tool on the MCP server."""

    @mcp.tool()
    def list_code_wiki_topics(repo_url: str) -> str:
        """
        Retrieve the overview / available topics for a repository from Google CodeWiki.

        Use this to discover what CodeWiki knows about a repo before asking
        specific questions with ``search_code_wiki``.

        Returns section titles with short content previews (not the full page).
        For detailed content, call ``read_wiki_contents`` with a section title.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/microsoft/vscode-copilot-chat)
                      or shorthand owner/repo (e.g. microsoft/vscode-copilot-chat).
        """
        start = time.monotonic()
        logger.info("list_code_wiki_topics — repo: %s", repo_url)

        result = fetch_page_or_error(repo_url)
        if isinstance(result, ToolResponse):
            return result.to_text()

        page = result
        data = page_to_topic_list(
            page, preview_chars=config.TOPIC_PREVIEW_CHARS,
        )
        data, truncated = truncate_response(data, config.RESPONSE_MAX_CHARS)
        elapsed = int((time.monotonic() - start) * 1000)

        return ToolResponse.success(
            data,
            repo_url=page.url,
            meta=ResponseMeta(
                elapsed_ms=elapsed,
                char_count=len(data),
                truncated=truncated,
            ),
        ).to_text()
