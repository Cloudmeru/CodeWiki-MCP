"""read_wiki_structure tool — Lightweight JSON table of contents.

The most token-efficient tool — returns structured metadata only.
Always call this first to discover section titles before reading content.
"""

from __future__ import annotations

import json
import logging
import time

from mcp.server.fastmcp import FastMCP

from ..types import ResponseMeta, ToolResponse
from ._helpers import fetch_page_or_error

logger = logging.getLogger("CodeWiki")


def register(mcp: FastMCP) -> None:
    """Register the read_wiki_structure tool on the MCP server."""

    @mcp.tool()
    def read_wiki_structure(repo_url: str) -> str:
        """
        Get a list of documentation topics for a repository from Google CodeWiki.

        Returns the table of contents / section structure as a JSON list so you
        can choose which sections to read with ``read_wiki_contents``.

        **Recommended first step** — call this before ``read_wiki_contents``
        or ``list_code_wiki_topics`` to discover available sections without
        consuming many tokens.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/facebook/react)
                      or shorthand owner/repo (e.g. facebook/react).
        """
        start = time.monotonic()
        logger.info("read_wiki_structure — repo: %s", repo_url)

        result = fetch_page_or_error(repo_url)
        if isinstance(result, ToolResponse):
            return result.to_text()

        page = result

        # Build structured TOC
        structure = {
            "repo": page.repo_name,
            "title": page.title,
            "sections": [
                {"title": s.title, "level": s.level} for s in page.sections
            ],
            "section_count": len(page.sections),
        }

        data = json.dumps(structure, indent=2)
        elapsed = int((time.monotonic() - start) * 1000)

        return ToolResponse.success(
            data,
            repo_url=page.url,
            meta=ResponseMeta(
                elapsed_ms=elapsed,
                char_count=len(data),
            ),
        ).to_text()
