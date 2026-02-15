---
name: codewiki-research
description: >
  Research and understand open-source codebases using Google CodeWiki
  via MCP. Use when the user asks about a GitHub repository's
  architecture, code structure, implementation details, or
  documentation. Supports any public GitHub, GitLab, or Bitbucket repo.
---

# CodeWiki Research Skill

You have access to CodeWiki MCP tools to explore open-source repository
documentation powered by Google CodeWiki and Gemini AI.

## Available Tools

Use these MCP tools (provided by the `codewiki-mcp` server):

1. **list_code_wiki_topics** — Discover what documentation exists for a repo
2. **read_wiki_structure** — Get the table of contents as JSON
3. **read_wiki_contents** — Read full wiki or a specific section
4. **search_code_wiki** — Ask Gemini a natural-language question about the repo

## Recommended Workflow

1. Start with `list_code_wiki_topics(repo_url)` to see if the repo is indexed
2. Call `read_wiki_structure(repo_url)` to get section titles
3. Call `read_wiki_contents(repo_url, section_title)` for the relevant section
4. Use `search_code_wiki(repo_url, query)` for specific implementation questions
5. Synthesize results into a clear, cited answer

## Input Format

- `repo_url`: Use `owner/repo` shorthand (e.g., `microsoft/vscode`) or a full URL
- `section_title`: Partial or full match of a section title (optional)
- `query`: Natural language question (for search only)

## Guidelines

- Always cite which section your answer comes from
- If no content exists for a repo, inform the user honestly
- Prefer section reads for broad topics, search for specific questions
- First calls may take 5-15s (Playwright render); subsequent calls are cached