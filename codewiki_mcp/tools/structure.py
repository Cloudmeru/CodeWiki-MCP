"""read_wiki_structure tool — Get a list of documentation topics for a repository.

Uses Playwright to render the JS SPA, then BeautifulSoup to parse sections.
"""

from __future__ import annotations

import json
import logging
import time

from mcp.server.fastmcp import FastMCP

from ..parser import fetch_wiki_page
from ..types import (
    ErrorCode,
    ResponseMeta,
    ToolResponse,
    validate_topics_input,
)

logger = logging.getLogger("CodeWiki")


def register(mcp: FastMCP) -> None:
    """Register the read_wiki_structure tool on the MCP server."""

    @mcp.tool()
    def read_wiki_structure(repo_url: str) -> str:
        """
        Get a list of documentation topics for a repository from Google CodeWiki.

        Returns the table of contents / section structure as a JSON list so you
        can choose which sections to read with ``read_wiki_contents``.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/facebook/react)
                      or shorthand owner/repo (e.g. facebook/react).
        """
        start = time.monotonic()
        logger.info("read_wiki_structure — repo: %s", repo_url)

        validated = validate_topics_input(repo_url)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        try:
            page = fetch_wiki_page(validated.repo_url)

            if not page.toc and not page.sections:
                return ToolResponse.error(
                    ErrorCode.NO_CONTENT,
                    f"No content found for {validated.repo_url}. "
                    "The repository may not be indexed by CodeWiki.",
                    repo_url=validated.repo_url,
                ).to_text()

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
                repo_url=validated.repo_url,
                meta=ResponseMeta(
                    elapsed_ms=elapsed,
                    char_count=len(data),
                ),
            ).to_text()

        except TimeoutError as exc:
            return ToolResponse.error(
                ErrorCode.TIMEOUT,
                f"Timed out fetching CodeWiki page for {validated.repo_url}: {exc}",
                repo_url=validated.repo_url,
            ).to_text()
        except Exception as exc:  # pylint: disable=broad-except
            return ToolResponse.error(
                ErrorCode.INTERNAL,
                f"Failed to fetch CodeWiki page: {exc}",
                repo_url=validated.repo_url,
            ).to_text()
