# PRD — GitHub Direct MCP Server

## 1) Product Overview
Create a standalone MCP server that lets LLM agents query GitHub repositories directly (read file, list directory, local code search) **without cloning repos**.

## 2) Problem Statement
CodeWiki explanations are useful but sometimes require source-level verification. Agents need a direct, deterministic way to fetch file content and structure from GitHub to answer follow-up questions accurately.

## 3) Goals
- Provide direct access to public GitHub repository contents.
- Avoid `git clone` and local repo management complexity.
- Keep responses structured, bounded, and LLM-safe.
- Offer local MCP-side code search over fetched snapshots.

## 4) Non-Goals (MVP)
- No private repo support in v1.
- No GitHub write operations (create/edit/commit/PR).
- No GitHub-native code search API dependency.
- No GitLab/Bitbucket support in v1.

## 5) Users
- LLM agents using MCP tools
- Developers needing source-grounded follow-up after CodeWiki summaries

## 6) MVP Tools
1. `github_read_file`
2. `github_list_directory`
3. `github_search_code_local`

## 7) Functional Requirements
- Accept `owner/repo` and optional `ref` (branch/tag/commit SHA).
- Return UTF-8 text file contents under configured size limits.
- Detect binary/oversized files and return metadata-only error/info.
- List directory contents with file type metadata.
- Build/query local searchable snapshot for text files only.
- Return consistent JSON envelope: `status`, `data`, `meta`, error `code`.

## 8) Non-Functional Requirements
- Timeouts and retry with backoff for API calls.
- Configurable limits for file size, result counts, index size.
- Deterministic response truncation policy.
- Safe defaults for unauthenticated GitHub API limits.

## 9) Success Metrics
- ≥95% success rate for valid public repo reads within limits.
- P50 read latency < 1.5s, P95 < 5s (network-dependent).
- Local search result relevance acceptable for top-10 hits.
- Zero secret leakage in logs/responses.

## 10) Risks
- GitHub unauthenticated rate limits.
- Large repositories exceeding indexing constraints.
- False confidence from partial/truncated content.

## 11) Milestones
- M1: Read/list tools + tests
- M2: Local search indexing + tests
- M3: Docs, examples, hardening
