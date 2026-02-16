# CodeWiki MCP Server

<p align="center">
  <img src="docs/favicon.svg" alt="CodeWiki MCP logo" width="96" height="96">
</p>

<p align="center">
  <a href="https://pypi.org/project/codewiki-mcp/"><img src="https://img.shields.io/pypi/v/codewiki-mcp" alt="PyPI"></a>
  <a href="https://github.com/Cloudmeru/CodeWiki-MCP/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Cloudmeru/CodeWiki-MCP" alt="License"></a>
  <a href="https://python.org"><img src="https://img.shields.io/pypi/pyversions/codewiki-mcp" alt="Python"></a>
</p>

An [MCP](https://modelcontextprotocol.io/) server that brings [Google CodeWiki](https://codewiki.google/) into your editor. Query any GitHub, GitLab, or Bitbucket repository and get AI-generated answers about the codebase — powered by Gemini.

**[Documentation](https://cloudmeru.github.io/CodeWiki-MCP)** · **[Release Notes](https://cloudmeru.github.io/CodeWiki-MCP/release-notes.html)** · **[PyPI](https://pypi.org/project/codewiki-mcp/)**

---

## Quick Start

```bash
pip install codewiki-mcp
playwright install chromium
```

## Client Setup

### VS Code

Open **Command Palette** (`Ctrl+Shift+P`) → **MCP: Add Server** → **Command (stdio)** → enter `codewiki-mcp`.

Or add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "codewikiMcp": {
      "type": "stdio",
      "command": "codewiki-mcp"
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "codewiki-mcp"
    }
  }
}
```

### Docker

```bash
docker build -t codewiki-mcp .
docker run -it --rm codewiki-mcp
```

## Tools

| Tool | Description |
|------|-------------|
| `codewiki_list_topics` | Topics overview with previews |
| `codewiki_read_structure` | JSON table of contents |
| `codewiki_read_contents` | Full or section-specific docs (paginated) |
| `codewiki_search_wiki` | Gemini-powered Q&A chat |
| `codewiki_request_indexing` | Submit unindexed repos for indexing |

All tools accept `repo_url` as a full URL or `owner/repo` shorthand.

## Documentation

Configuration, architecture, agentic AI guides, and more — see the **[full documentation](https://cloudmeru.github.io/CodeWiki-MCP)**.

## License

MIT
