# CodeWiki MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides AI-powered access to [Google CodeWiki](https://codewiki.google/) for open-source repositories. Query any GitHub, GitLab, or Bitbucket repository and get instant, AI-generated answers about the codebase — all from your editor.

## Features

- **Playwright-powered rendering** — CodeWiki is an Angular SPA; all page content is rendered via headless Chromium
- **4 MCP tools** — topics overview, structure (JSON TOC), full/section content, interactive Gemini chat Q&A
- **Shared browser singleton** — persistent background event loop with lazy Chromium launch, shared across all tools
- **In-memory caching** — TTLCache avoids redundant page renders (wiki pages cached for 5 min)
- **Dual-strategy parser** — handles CodeWiki's custom Angular elements (`<body-content-section>`, `<documentation-markdown>`) with fallback to standard HTML
- **Pydantic input validation** — schema-based validation with clear error messages
- **Structured JSON responses** — `{status, code, message, data, meta}` envelope
- **URL normalization** — accepts `owner/repo` shorthand or full URLs
- **Environment variable configuration** — override timeouts, retries, cache TTL, and limits
- **Multi-transport** — stdio (default) or SSE
- **Modular architecture** — tools in separate modules, easy to extend
- **Response metadata** — timing, char count, attempt info in every response
- **Docker support** — Dockerfile with Playwright included

## Prerequisites

- Python 3.10+
- Playwright Chromium (`playwright install chromium`)

## Installation

### Option A — Install as a CLI command (recommended)

```bash
pip install .
playwright install chromium

# Now you can run:
codewiki-mcp
codewiki-mcp --sse --port 8080
codewiki-mcp --verbose
```

### Option B — Install dependencies only

```bash
pip install mcp pydantic httpx beautifulsoup4 lxml playwright cachetools
playwright install chromium

python -m codewiki_mcp
```

### Option C — Build a standalone `.exe`

```bash
pip install ".[build]"
python build_exe.py
# → dist/codewiki-mcp.exe (Windows) or dist/codewiki-mcp (macOS/Linux)
```

> **Note:** The `.exe` still requires Playwright Chromium on the target machine for the chat tool.

### Option D — Docker

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
| `CODEWIKI_RESPONSE_MAX_CHARS` | `8000` | Max response character count |
| `CODEWIKI_CACHE_TTL` | `300` | Page cache TTL (seconds) |
| `CODEWIKI_CACHE_MAX_SIZE` | `50` | Max pages in cache |
| `CODEWIKI_VERBOSE` | `false` | Enable debug logging |
| `CODEWIKI_BASE_URL` | `https://codewiki.google` | CodeWiki base URL |

### MCP Client Setup

**VS Code** (`.vscode/mcp.json`):
```json
{
  "mcpServers": {
    "codewiki": {
      "command": "codewiki-mcp"
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):
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
├── driver.py          # Deprecated Selenium shim (no-op)
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
├── conftest.py        # Shared fixtures + sample data
├── test_cache.py      # Cache layer tests
├── test_config.py     # Configuration tests
├── test_parser.py     # Parser + HTML extraction tests
├── test_tools.py      # Server, tools & integration tests
└── test_types.py      # Schema & response tests
Dockerfile             # Docker deployment
```

## Running Tests

```bash
pip install -e ".[test]"
pytest tests/ -v
```

## Architecture

### v0.3.0 — Playwright-everywhere

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

#### Key components

- **Playwright + shared browser** — all page rendering via headless Chromium
- **TTLCache** — rendered pages cached for 5 minutes (configurable)
- **BeautifulSoup + lxml** — fast HTML parsing with section extraction, TOC, and diagram detection
- **Pydantic schemas** validate all inputs before processing
- **Structured responses** with JSON envelope and metadata
- **Modular tools** — each tool in its own module, registered via `register_all_tools()`
- **Environment variable configuration** — all tunables configurable without code changes
