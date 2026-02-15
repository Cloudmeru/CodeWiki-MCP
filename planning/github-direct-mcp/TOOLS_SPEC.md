# Tool Specifications — GitHub Direct MCP Server

## Common Response Envelope
```json
{
  "status": "ok|error",
  "code": "OPTIONAL_ERROR_CODE",
  "message": "human-readable",
  "data": {},
  "meta": {
    "elapsed_ms": 0,
    "truncated": false,
    "source": "github-api|local-index"
  }
}
```

## 1) `github_read_file`
Reads a file from a public GitHub repository.

### Input
- `repo`: string (`owner/repo`)
- `path`: string
- `ref`: string (optional)

### Output `data`
- `repo`, `path`, `ref`
- `content` (text, possibly truncated)
- `encoding` (usually `utf-8`)
- `size_bytes`

### Errors
- `NOT_FOUND`, `BINARY_FILE`, `TOO_LARGE`, `RATE_LIMIT`, `TIMEOUT`, `UPSTREAM_ERROR`

---

## 2) `github_list_directory`
Lists one directory level in a public GitHub repository.

### Input
- `repo`: string (`owner/repo`)
- `path`: string (optional, default root)
- `ref`: string (optional)

### Output `data`
- `repo`, `path`, `ref`
- `entries`: array of `{name, path, type, size_bytes?}` where type is `file|dir|symlink|submodule`

### Errors
- `NOT_FOUND`, `RATE_LIMIT`, `TIMEOUT`, `UPSTREAM_ERROR`

---

## 3) `github_search_code_local`
Searches code locally within an MCP-managed snapshot fetched from GitHub.

### Input
- `repo`: string (`owner/repo`)
- `query`: string
- `ref`: string (optional)
- `path_prefix`: string (optional)
- `max_results`: integer (optional, default 20, max 100)

### Output `data`
- `repo`, `ref`, `query`
- `results`: array of
  - `path`
  - `score`
  - `snippet`
  - `line_start`, `line_end`
- `index_stats`: `{files_indexed, bytes_indexed, built_at}`

### Errors
- `VALIDATION`, `RATE_LIMIT`, `TIMEOUT`, `UPSTREAM_ERROR`, `INTERNAL`

## Notes
- This tool does **not** call GitHub search APIs in MVP.
- Search executes in the MCP server over fetched snapshot data.
