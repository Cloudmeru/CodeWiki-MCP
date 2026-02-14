"""read_wiki_contents tool — View full or section-specific documentation.

Uses Playwright to render the JS SPA, then BeautifulSoup to parse content.
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import FastMCP

from .. import config
from ..parser import fetch_wiki_page, get_section_by_title, page_to_markdown
from ..types import (
    ErrorCode,
    ResponseMeta,
    ToolResponse,
    validate_section_input,
    validate_topics_input,
)

logger = logging.getLogger("CodeWiki")


def register(mcp: FastMCP) -> None:
    """Register the read_wiki_contents tool on the MCP server."""

    @mcp.tool()
    def read_wiki_contents(repo_url: str, section_title: str = "") -> str:
        """
        View documentation about a GitHub repository from Google CodeWiki.

        Without ``section_title``, returns the full wiki content (may be truncated).
        With ``section_title``, returns just that section's content.

        Use ``read_wiki_structure`` first to see available sections.

        Args:
            repo_url: Full repository URL (e.g. https://github.com/facebook/react)
                      or shorthand owner/repo (e.g. facebook/react).
            section_title: Optional. Title (or partial title) of a specific section
                          to retrieve. If empty, returns the full wiki.
        """
        start = time.monotonic()
        logger.info("read_wiki_contents — repo: %s, section: %s", repo_url, section_title)

        # Validate input based on whether section is specified
        if section_title.strip():
            validated = validate_section_input(repo_url, section_title)
        else:
            validated = validate_topics_input(repo_url)

        if isinstance(validated, ToolResponse):
            return validated.to_text()

        try:
            page = fetch_wiki_page(validated.repo_url)

            if not page.sections and not page.raw_text:
                return ToolResponse.error(
                    ErrorCode.NO_CONTENT,
                    f"No content found for {validated.repo_url}. "
                    "The repository may not be indexed by CodeWiki.",
                    repo_url=validated.repo_url,
                ).to_text()

            # If section requested, find it
            if section_title.strip():
                section = get_section_by_title(page, section_title)
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
                # Full page as markdown
                data = page_to_markdown(page, max_chars=config.RESPONSE_MAX_CHARS)

            truncated = False
            if len(data) > config.RESPONSE_MAX_CHARS:
                data = data[: config.RESPONSE_MAX_CHARS] + "\n\n... [truncated]"
                truncated = True

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

        except TimeoutError as exc:
            return ToolResponse.error(
                ErrorCode.TIMEOUT,
                f"Timed out fetching CodeWiki page for {validated.repo_url}: {exc}",
                repo_url=validated.repo_url,
            ).to_text()
        except Exception as exc:
            return ToolResponse.error(
                ErrorCode.INTERNAL,
                f"Failed to fetch CodeWiki page: {exc}",
                repo_url=validated.repo_url,
            ).to_text()
