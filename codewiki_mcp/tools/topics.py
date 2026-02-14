"""list_code_wiki_topics tool — Legacy-compatible overview tool.

Retained for backward compatibility. Uses httpx + parser instead of Selenium.
For structured output, prefer read_wiki_structure / read_wiki_contents.
"""

from __future__ import annotations

import logging
import time

from mcp.server.fastmcp import FastMCP

from .. import config
from ..parser import fetch_wiki_page, page_to_markdown
from ..types import (
    ErrorCode,
    ResponseMeta,
    ToolResponse,
    validate_topics_input,
)

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

        Args:
            repo_url: Full repository URL (e.g. https://github.com/microsoft/vscode-copilot-chat)
                      or shorthand owner/repo (e.g. microsoft/vscode-copilot-chat).
        """
        start = time.monotonic()
        logger.info("list_code_wiki_topics — repo: %s", repo_url)

        validated = validate_topics_input(repo_url)
        if isinstance(validated, ToolResponse):
            return validated.to_text()

        try:
            page = fetch_wiki_page(validated.repo_url)

            if not page.raw_text:
                return ToolResponse.error(
                    ErrorCode.NO_CONTENT,
                    f"No content found for {validated.repo_url}. "
                    "The repository may not be indexed by CodeWiki.",
                    repo_url=validated.repo_url,
                ).to_text()

            # Return full page as markdown (truncated if needed)
            data = page_to_markdown(page, max_chars=config.RESPONSE_MAX_CHARS)

            truncated = len(data) >= config.RESPONSE_MAX_CHARS
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
        except Exception as exc:  # pylint: disable=broad-except
            return ToolResponse.error(
                ErrorCode.INTERNAL,
                f"Failed to fetch CodeWiki page: {exc}",
                repo_url=validated.repo_url,
            ).to_text()
