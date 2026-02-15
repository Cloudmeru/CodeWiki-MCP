"""read_wiki_contents tool — View full or section-specific documentation.

Uses Playwright to render the JS SPA, then BeautifulSoup to parse content.
Supports pagination to avoid overwhelming the context window.
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import FastMCP

from .. import config
from ..parser import get_section_by_title
from ..types import (
    ErrorCode,
    ResponseMeta,
    ToolResponse,
    validate_contents_input,
)
from ._helpers import fetch_page_or_error, truncate_response

logger = logging.getLogger("CodeWiki")


def register(mcp: FastMCP) -> None:
    """Register the read_wiki_contents tool on the MCP server."""

    @mcp.tool()
    def read_wiki_contents(
        repo_url: str,
        section_title: str = "",
        offset: int = 0,
        limit: int = 5,
    ) -> str:
        """
        View documentation about a GitHub repository from Google CodeWiki.

        Without ``section_title``, returns the full wiki content (may be truncated).
        With ``section_title``, returns just that section's content.

        Use ``read_wiki_structure`` first to see available sections.

        **Pagination** (when ``section_title`` is empty):
        - ``offset`` — section index to start from (default 0).
        - ``limit`` — max sections per response (default 5).
        The response includes ``has_more`` and ``next_offset`` when more
        sections are available, so you can call again to continue.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/facebook/react)
                      or shorthand owner/repo (e.g. facebook/react).
            section_title: Optional. Title (or partial title) of a specific section
                          to retrieve. If empty, returns the full wiki.
            offset: Section index to start from (0-based, default 0).
            limit: Maximum sections to return (default 5, max 50).
        """
        start = time.monotonic()
        logger.info(
            "read_wiki_contents — repo: %s, section: %s, offset: %d, limit: %d",
            repo_url,
            section_title,
            offset,
            limit,
        )

        validated = validate_contents_input(repo_url, section_title, offset, limit)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        result = fetch_page_or_error(validated.repo_url)
        if isinstance(result, ToolResponse):
            return result.to_text()

        page = result

        # ----- Section-specific path -----
        if validated.section_title.strip():
            section = get_section_by_title(page, validated.section_title)
            if section is None:
                available = [s.title for s in page.sections[:20]]
                return ToolResponse.error(
                    ErrorCode.NO_CONTENT,
                    f"Section '{section_title}' not found. "
                    f"Available sections: {', '.join(available)}",
                    repo_url=validated.repo_url,
                ).to_text()

            prefix = "#" * min(section.level + 1, 6)
            data = f"{prefix} {section.title}\n\n{section.content}"
        else:
            # ----- Paginated full-page path -----
            total = len(page.sections)
            sliced = page.sections[validated.offset : validated.offset + validated.limit]
            has_more = (validated.offset + validated.limit) < total

            parts = [f"# {page.title}\n"]
            for section in sliced:
                pfx = "#" * min(section.level + 1, 6)
                parts.append(f"\n{pfx} {section.title}\n")
                if section.content:
                    parts.append(section.content)

            if has_more:
                next_off = validated.offset + validated.limit
                parts.append(
                    f"\n\n---\n*Showing sections {validated.offset + 1}–"
                    f"{validated.offset + len(sliced)} of {total}. "
                    f"Call again with `offset={next_off}` to continue.*"
                )

            data = "\n".join(parts).strip()

        data, truncated = truncate_response(data, config.RESPONSE_MAX_CHARS)
        elapsed = int((time.monotonic() - start) * 1000)

        return ToolResponse.success(
            data,
            repo_url=validated.repo_url,
            meta=ResponseMeta(
                elapsed_ms=elapsed,
                char_count=len(data),
                truncated=truncated,
            ),
        ).to_text()
