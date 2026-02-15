# Implementation Plan (Separate Project)

## Phase 0 — Project Scaffold
- Create standalone repo/package for new MCP server.
- Add base MCP server wiring, config module, types module.
- Add lint/test CI baseline.

## Phase 1 — Direct Read/List (MVP Core)
- Implement GitHub client for public contents endpoints.
- Implement `github_read_file` and `github_list_directory`.
- Add retries, timeout, rate-limit handling.
- Add cache for file/directory payloads.
- Unit tests for success + failure paths.

## Phase 2 — Local Search Layer
- Build snapshot fetch + index pipeline (no clone).
- Implement `github_search_code_local` with ranking.
- Add configurable caps and extension allowlist.
- Add tests for indexing boundaries and query quality.

## Phase 3 — DX and Hardening
- Add docs, examples, and integration usage patterns.
- Add observability fields in `meta` (attempts, cache hit).
- Performance tuning and cache/index tuning defaults.

## Acceptance Criteria
- All three tools return standardized envelope.
- Public repos work without authentication.
- Oversized/binary files are safely handled.
- Search returns grounded path+snippet outputs.
