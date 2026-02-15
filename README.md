# CodeWiki MCP Server

<p align="left">
  <img src="docs/favicon.svg" alt="CodeWiki MCP logo" width="64" height="64">
</p>

Documentation: [https://cloudmeru.github.io/CodeWiki-MCP](https://cloudmeru.github.io/CodeWiki-MCP)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides AI-powered access to [Google CodeWiki](https://codewiki.google/) for open-source repositories. Query any GitHub, GitLab, or Bitbucket repository and get instant, AI-generated answers about the codebase — all from your editor.

## Features

- **Playwright-powered rendering** — CodeWiki is an Angular SPA; all page content is rendered via headless Chromium
- **4 MCP tools** — topics overview, structure (JSON TOC), full/section content, interactive Gemini chat Q&A
- **Structured diagram extraction** — detects CodeWiki SPA diagrams, Mermaid blocks, and inline SVGs; parses Graphviz SVGs into entities and relationships
- **Shared browser singleton** — persistent background event loop with lazy Chromium launch, shared across all tools
- **In-memory caching** — TTLCache avoids redundant page renders (wiki pages cached for 5 min)
- **Dual-strategy parser** — handles CodeWiki's custom Angular elements (`<body-content-section>`, `<documentation-markdown>`) with fallback to standard HTML
- **Pydantic input validation** — schema-based validation with clear error messages
- **Structured JSON responses** — `{status, code, message, data, meta}` envelope
- **URL normalization** — accepts `owner/repo` shorthand or full URLs
- **Environment variable configuration** — override timeouts, retries, cache TTL, and limits
- **Multi-transport** — stdio (default) or SSE
- **Graceful shutdown** — SIGINT/SIGTERM handlers for clean Ctrl+C
- **Modular architecture** — tools in separate modules, easy to extend
- **Response metadata** — timing, char count, attempt info in every response
- **Docker support** — Dockerfile with Playwright included

## Prerequisites

- Python 3.10+
- Playwright Chromium (`playwright install chromium`)

## Installation

### Option A — Install from PyPI (recommended)

```bash
pip install codewiki-mcp
playwright install chromium
```

That's it. You now have the `codewiki-mcp` command available globally:

```bash
codewiki-mcp                    # stdio (default)
codewiki-mcp --sse --port 8080  # SSE transport
codewiki-mcp --verbose           # debug logging
```

### Option B — Install from source

```bash
git clone https://github.com/Cloudmeru/CodeWiki-MCP.git
cd CodeWiki-MCP
pip install .
playwright install chromium
```

For development (with test dependencies):

```bash
pip install -e ".[test]"
```

### Option C — Docker

```bash
docker build -t codewiki-mcp .

# stdio (for MCP clients)
docker run -it --rm codewiki-mcp

# SSE (for HTTP access)
docker run -p 3000:3000 codewiki-mcp --sse --port 3000

# With custom config
docker run -e CODEWIKI_MAX_RETRIES=5 -e CODEWIKI_VERBOSE=true codewiki-mcp
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEWIKI_HARD_TIMEOUT` | `60` | Hard timeout per request (seconds) |
| `CODEWIKI_HTTPX_TIMEOUT` | `30` | HTTP timeout fallback (seconds) |
| `CODEWIKI_PAGE_LOAD_TIMEOUT` | `30` | Playwright page load timeout (seconds) |
| `CODEWIKI_ELEMENT_WAIT_TIMEOUT` | `20` | Element wait timeout (seconds) |
| `CODEWIKI_RESPONSE_WAIT_TIMEOUT` | `45` | Chat response wait timeout (seconds) |
| `CODEWIKI_MAX_RETRIES` | `2` | Max retry attempts |
| `CODEWIKI_RETRY_DELAY` | `3` | Delay between retries (seconds) |
| `CODEWIKI_RESPONSE_MAX_CHARS` | `30000` | Max response character count |
| `CODEWIKI_CACHE_TTL` | `300` | Page cache TTL (seconds) |
| `CODEWIKI_CACHE_MAX_SIZE` | `50` | Max pages in cache |
| `CODEWIKI_RESPONSE_INITIAL_DELAY` | `5` | Initial delay before polling chat response (seconds) |
| `CODEWIKI_RESPONSE_POLL_INTERVAL` | `2` | Interval between chat response polls (seconds) |
| `CODEWIKI_RESPONSE_STABLE_INTERVAL` | `2` | Stable response detection interval (seconds) |
| `CODEWIKI_JS_LOAD_DELAY` | `3` | Delay for JS/SPA loading (seconds) |
| `CODEWIKI_VERBOSE` | `false` | Enable debug logging |
| `CODEWIKI_BASE_URL` | `https://codewiki.google` | CodeWiki base URL |

### MCP Client Setup

#### VS Code — Command Palette (recommended)

The fastest way to add CodeWiki MCP to VS Code:

1. Open the **Command Palette** — press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS)
2. Type **MCP** and select **MCP: Add Server**
3. Choose **Command (stdio)** as the server type
4. Enter the command: `codewiki-mcp`
5. Enter a server ID — e.g. `codewikiMcp` (VS Code recommends camelCase)
6. Select a configuration scope:
   - **User** — available across all VS Code workspaces (saved in your global user `mcp.json`)
   - **Workspace** — available only in the current workspace (saved in `.vscode/mcp.json`)
7. VS Code creates and opens the `mcp.json` file — click **Start** above the server name to launch it
8. When prompted, confirm that you trust the server

> **Tip:** Use **MCP: List Servers** from the Command Palette to start, stop, restart, or view logs for any configured server.

#### VS Code — Manual JSON config

Alternatively, create or edit `.vscode/mcp.json` in your workspace root:

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

#### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codewiki": {
      "command": "codewiki-mcp"
    }
  }
}
```

## CLI Options

```
codewiki-mcp [--stdio | --sse] [--port PORT] [--verbose | -v]
```

| Flag | Description |
|------|-------------|
| `--stdio` | Run with stdio transport (default) |
| `--sse` | Run with SSE transport |
| `--port PORT` | Port for SSE transport (default: 3000) |
| `--verbose`, `-v` | Enable debug logging |

## Tools

### `list_code_wiki_topics`

Retrieve the overview and available topics for a repository. Returns the full wiki content as markdown.

| Parameter  | Type   | Required | Description |
|------------|--------|----------|-------------|
| `repo_url` | string | Yes      | Full URL or `owner/repo` shorthand |

*Renders the page via Playwright, caches result for 5 minutes.*

### `read_wiki_structure`

Get a JSON list of documentation sections/topics for a repository. Use this to see what's available before reading specific sections.

| Parameter  | Type   | Required | Description |
|------------|--------|----------|-------------|
| `repo_url` | string | Yes      | Full URL or `owner/repo` shorthand |

*Renders the page via Playwright, caches result for 5 minutes.*

### `read_wiki_contents`

View full or section-specific documentation. Without `section_title`, returns the full wiki (may be truncated). With `section_title`, returns just that section.

| Parameter       | Type   | Required | Description |
|-----------------|--------|----------|-------------|
| `repo_url`      | string | Yes      | Full URL or `owner/repo` shorthand |
| `section_title` | string | No       | Title (or partial) of a section to retrieve |

*Renders the page via Playwright, caches result for 5 minutes.*

### `search_code_wiki`

Ask Google CodeWiki a question about an open-source repository. Uses the interactive Gemini-powered chat.

| Parameter  | Type   | Required | Description |
|------------|--------|----------|-------------|
| `repo_url` | string | Yes      | Full URL or `owner/repo` shorthand |
| `query`    | string | Yes      | The question to ask |

*Opens a new browser context, interacts with the chat panel, waits for the streamed Gemini response.*

**Examples:**
```
repo_url: https://github.com/microsoft/vscode-copilot-chat
query: Where are the Allow/Skip buttons implemented?

repo_url: microsoft/vscode
query: How does the extension activation work?
```

### Response Format

All tools return structured JSON:

```json
{
  "status": "ok",
  "data": "The response content...",
  "repo_url": "https://github.com/owner/repo",
  "query": "How does X work?",
  "meta": {
    "elapsed_ms": 450,
    "char_count": 3200,
    "attempt": 1,
    "max_attempts": 2,
    "truncated": false
  }
}
```

Error responses:
```json
{
  "status": "error",
  "code": "TIMEOUT",
  "message": "Page took too long to load.",
  "repo_url": "https://github.com/owner/repo",
  "meta": { "elapsed_ms": 60000, "attempt": 2, "max_attempts": 2 }
}
```

Error codes: `VALIDATION`, `TIMEOUT`, `DRIVER_ERROR`, `NO_CONTENT`, `INPUT_NOT_FOUND`, `INTERNAL`, `RETRY_EXHAUSTED`

## Project Structure

```
codewiki_mcp/
├── __init__.py        # Package init + version
├── __main__.py        # python -m entry point
├── browser.py         # Shared Playwright browser singleton + persistent event loop
├── cache.py           # TTLCache for rendered pages
├── config.py          # Env-var-driven configuration + SPA selectors
├── parser.py          # Playwright renderer + BeautifulSoup section parser
├── server.py          # MCP server setup + CLI
├── types.py           # Pydantic schemas + response models
└── tools/
    ├── __init__.py    # Tool registration
    ├── contents.py    # read_wiki_contents
    ├── search.py      # search_code_wiki (Playwright chat interaction)
    ├── structure.py   # read_wiki_structure
    └── topics.py      # list_code_wiki_topics
tests/
├── __init__.py        # Package marker
├── conftest.py        # Shared fixtures + sample data
├── test_cache.py      # Cache layer tests
├── test_config.py     # Configuration tests
├── test_parser.py     # Parser + HTML extraction tests
├── test_tools.py      # Server, tools & integration tests
└── test_types.py      # Schema & response tests
Dockerfile             # Docker deployment
```

```bash
pip install -e ".[test]"
pytest tests/ -v
```

## Architecture

### v1.0.0 — Playwright-everywhere

CodeWiki is an **Angular SPA** (`<sdlc-agents-root>`) — a plain HTTP GET returns an empty body. All page content is rendered client-side, so every tool uses Playwright headless Chromium.

#### Browser singleton

A **persistent background event loop** runs in a daemon thread. `browser.py` provides:
- `_get_browser()` — lazily launches a shared Chromium instance
- `run_in_browser_loop(coro)` — submits async work to the persistent loop from any sync context
- `fetch_rendered_html(url)` — navigates, waits for SPA content markers, returns the rendered HTML

All 4 tools share the same browser instance. Pages are cached in a TTLCache (5 min) so repeated requests skip the render.

#### SPA-aware parser

CodeWiki uses custom Angular elements instead of standard HTML:
- `<body-content-section>` — one per wiki section
- `<documentation-markdown>` — rendered markdown inside each section
- `<chat>` → `<new-message-form>` → `<textarea data-test-id="chat-input">` — the Gemini chat

`parser.py` implements a **dual-strategy section extractor**:
1. **CodeWiki SPA** — looks for `<body-content-section>` + `<documentation-markdown>` elements
2. **Standard HTML fallback** — scans h1-h6 headings for non-CodeWiki pages

#### Structured diagram extraction

CodeWiki renders diagrams as `<code-documentation-diagram-inline>` elements containing base64-encoded SVGs. The parser detects three types of diagrams:

1. **CodeWiki SPA diagrams** — decodes `data:image/svg+xml;base64,...` from `<image class="image-diagram">` elements, then parses Graphviz SVG structure
2. **Mermaid blocks** — captures raw source from `<code class="mermaid">` and `<div class="mermaid">`
3. **Fallback SVGs/images** — bare `<svg>` with `<title>` or `<img>` matching diagram patterns

For Graphviz SVGs, it extracts structured graph data:
- **Nodes** — `<g class="node">` groups → `{id, label}`
- **Edges** — `<g class="edge">` groups → `{from, to, label}`

Diagram summaries (entities + relationships) are placed at the top of tool output so they remain visible even when responses are truncated.

#### Key components

- **Playwright + shared browser** — all page rendering via headless Chromium
- **TTLCache** — rendered pages cached for 5 minutes (configurable)
- **BeautifulSoup + lxml** — fast HTML parsing with section extraction, TOC, and diagram detection
- **Pydantic schemas** validate all inputs before processing
- **Structured responses** with JSON envelope and metadata
- **Modular tools** — each tool in its own module, registered via `register_all_tools()`
- **Signal handlers** — SIGINT/SIGTERM for clean shutdown with browser cleanup
- **Environment variable configuration** — all tunables configurable without code changes
