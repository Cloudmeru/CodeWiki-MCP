"""Tests for MCP tool registration, server creation, and individual tools."""

from __future__ import annotations

import json


from codewiki_mcp.server import create_server, parse_args
from tests.conftest import make_wiki_page


# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------
class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.transport == "stdio"
        assert args.port == 3000
        assert args.verbose is False

    def test_sse(self):
        args = parse_args(["--sse", "--port", "8080"])
        assert args.transport == "sse"
        assert args.port == 8080

    def test_verbose(self):
        args = parse_args(["--verbose"])
        assert args.verbose is True

    def test_verbose_short(self):
        args = parse_args(["-v"])
        assert args.verbose is True


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------
class TestCreateServer:
    def test_returns_fastmcp(self):
        mcp = create_server()
        assert mcp is not None
        assert hasattr(mcp, "name") or hasattr(mcp, "_name")

    def test_tools_registered(self):
        """Verify all 4 tools are registered on the server."""
        mcp = create_server()
        assert mcp is not None


# ---------------------------------------------------------------------------
# list_code_wiki_topics tool
# ---------------------------------------------------------------------------
class TestTopicsTool:
    def test_success(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.topics.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        tools = {t.name: t for t in mcp._tool_manager.list_tools()}
        assert "list_code_wiki_topics" in tools

    def test_returns_json_envelope(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.topics.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        # Call the tool function directly
        fn = mcp._tool_manager._tools["list_code_wiki_topics"].fn
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "data" in parsed
        assert "meta" in parsed

    def test_no_content(self, mocker):
        page = make_wiki_page(raw_text="", sections=[])
        mocker.patch("codewiki_mcp.tools.topics.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["list_code_wiki_topics"].fn
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NO_CONTENT"

    def test_validation_error(self):
        from codewiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["list_code_wiki_topics"].fn
        result = fn(repo_url="bad")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_http_error(self, mocker):
        mocker.patch(
            "codewiki_mcp.tools.topics.fetch_wiki_page",
            side_effect=TimeoutError("Page render timed out"),
        )

        from codewiki_mcp.tools.topics import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["list_code_wiki_topics"].fn
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "TIMEOUT"


# ---------------------------------------------------------------------------
# read_wiki_structure tool
# ---------------------------------------------------------------------------
class TestStructureTool:
    def test_returns_json_sections(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.structure.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["read_wiki_structure"].fn
        result = fn(repo_url="microsoft/vscode")
        outer = json.loads(result)
        assert outer["status"] == "ok"

        inner = json.loads(outer["data"])
        assert inner["repo"] == "github.com/microsoft/vscode"
        assert inner["section_count"] == 4
        assert len(inner["sections"]) == 4

    def test_section_titles(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.structure.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.structure import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["read_wiki_structure"].fn
        result = fn(repo_url="microsoft/vscode")
        inner = json.loads(json.loads(result)["data"])
        titles = [s["title"] for s in inner["sections"]]
        assert "Architecture" in titles
        assert "Extensions" in titles
        assert "Testing" in titles


# ---------------------------------------------------------------------------
# read_wiki_contents tool
# ---------------------------------------------------------------------------
class TestContentsTool:
    def test_full_content(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.contents.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["read_wiki_contents"].fn
        result = fn(repo_url="microsoft/vscode")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Architecture" in parsed["data"]
        assert "Extensions" in parsed["data"]

    def test_section_filter(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.contents.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["read_wiki_contents"].fn
        result = fn(repo_url="microsoft/vscode", section_title="Architecture")
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Architecture" in parsed["data"]
        assert "Electron" in parsed["data"]

    def test_section_not_found(self, mocker):
        page = make_wiki_page()
        mocker.patch("codewiki_mcp.tools.contents.fetch_wiki_page", return_value=page)

        from codewiki_mcp.tools.contents import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["read_wiki_contents"].fn
        result = fn(repo_url="microsoft/vscode", section_title="Nonexistent Section")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "NO_CONTENT"
        assert "not found" in parsed["message"].lower()


# ---------------------------------------------------------------------------
# search_code_wiki tool (Playwright — mocked)
# ---------------------------------------------------------------------------
class TestSearchTool:
    def test_validation_error(self):
        from codewiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["search_code_wiki"].fn
        result = fn(repo_url="bad", query="test")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_empty_query_error(self):
        from codewiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["search_code_wiki"].fn
        result = fn(repo_url="microsoft/vscode", query="")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == "VALIDATION"

    def test_successful_search(self, mocker):
        """Mock _run_search to test the tool flow without Playwright."""
        from codewiki_mcp.types import ResponseMeta, ToolResponse

        mock_response = ToolResponse.success(
            "VS Code uses Electron for cross-platform support.",
            repo_url="https://github.com/microsoft/vscode",
            query="What framework does VS Code use?",
            meta=ResponseMeta(char_count=50),
        )
        mocker.patch(
            "codewiki_mcp.tools.search._run_search",
            return_value=mock_response,
        )

        from codewiki_mcp.tools.search import register
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test")
        register(mcp)

        fn = mcp._tool_manager._tools["search_code_wiki"].fn
        result = fn(
            repo_url="microsoft/vscode", query="What framework does VS Code use?"
        )
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert "Electron" in parsed["data"]
