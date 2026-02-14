"""Tool registration helpers for CodeWiki MCP.

5 tools available:
  - list_code_wiki_topics  — Legacy text overview (httpx)
  - read_wiki_structure    — JSON TOC/sections list (httpx)
  - read_wiki_contents     — Full or section-specific markdown (httpx)
  - search_code_wiki       — Interactive chat Q&A (Playwright)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register every CodeWiki tool on the given MCP server."""
    from .contents import register as register_contents
    from .search import register as register_search
    from .structure import register as register_structure
    from .topics import register as register_topics

    register_topics(mcp)
    register_structure(mcp)
    register_contents(mcp)
    register_search(mcp)
