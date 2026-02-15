# Architecture — GitHub Direct MCP Server

## High-Level Flow
1. MCP tool request arrives.
2. Input validator normalizes `owner/repo`, `path`, `ref`.
3. GitHub API client fetches metadata/content.
4. Content safety layer applies size/binary/truncation rules.
5. Optional snapshot index layer updates local search corpus.
6. Tool returns standardized response envelope.

## Components
- **Transport Layer**: MCP server tool registration/dispatch.
- **Validation Layer**: Pydantic input/output models.
- **GitHub Client**: REST calls to contents/tree endpoints.
- **Cache Layer**: TTL cache for file and listing payloads.
- **Index Layer**: local, in-memory/on-disk searchable snapshot.
- **Policy Layer**: limits, allowlists, truncation and errors.

## Data Sources
- GitHub REST API (public repos)
- Optional ZIP snapshot stream for large indexing workflows

## Error Model
Suggested codes:
- `VALIDATION`
- `NOT_FOUND`
- `RATE_LIMIT`
- `TIMEOUT`
- `TOO_LARGE`
- `BINARY_FILE`
- `UPSTREAM_ERROR`
- `INTERNAL`

## Security Model
- No token required in MVP.
- If token added later: env var only, never input arg.
- Never log full file payloads by default.
- Enforce max payload and index limits to reduce abuse risk.

## Caching Strategy
- Key: `{owner}/{repo}@{ref}:{path}`
- Separate namespaces for file content, directory listing, search index metadata.
- TTL configurable per namespace.

## Local Search Strategy (MVP)
- Index only text files matching extension allowlist.
- Hard caps: max files, max bytes per file, max aggregate bytes.
- Ranking: term frequency + path boost + filename match boost.
