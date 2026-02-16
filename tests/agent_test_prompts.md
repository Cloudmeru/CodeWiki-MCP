# CodeWiki Agent — Test Prompts

> **Purpose**: Sample prompts to test the master orchestrator agent
> (`codewiki.agent.md`) and verify it correctly delegates to each
> specialist subagent.
>
> **Usage**: Prefix each prompt with `@codewiki` in VS Code chat.
>
> **Important**: These prompts must be tested in the **VS Code Chat panel**
> (Ctrl+Shift+I), not in a regular Copilot inline chat or conversation.
> The `.agent.md` custom agents only activate when invoked via `@codewiki`
> in the Chat panel. The `runSubagent` tool in regular Copilot chat does
> NOT wire up MCP tools to subagents.
>
> **Prerequisites**:
> 1. The `codewiki-mcp` MCP server must be running and configured in
>    `.vscode/mcp.json` (included in this repo).
> 2. All 5 `.agent.md` files must be in `.github/agents/`.

---

## 1. CodeWiki Researcher (General Exploration)

**Routing trigger**: General "what is", "explain", "tell me about" questions.

### Prompts

```
@codewiki What is facebook/prophet and what are its main features?
```

```
@codewiki Explain the key concepts behind pallets/flask
```

```
@codewiki What topics does CodeWiki have for microsoft/vscode?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **CodeWiki Researcher** via the `agent` tool |
| 2 | Researcher calls `codewiki_list_topics` to discover available wiki sections |
| 3 | Researcher calls `codewiki_read_structure` and/or `codewiki_read_contents` |
| 4 | Researcher synthesises a summary from CodeWiki content |

### Validation

- [ ] Master does **not** answer from its own knowledge
- [ ] Master uses the `agent` tool (not direct tool calls)
- [ ] Researcher cites CodeWiki sections in its answer
- [ ] Response contains real documentation content, not generic descriptions

---

## 2. CodeWiki Code Review (Module / Function Analysis)

**Routing trigger**: "review", "analyse", "what does module X do", code-level questions.

### Prompts

```
@codewiki Review the forecaster module in facebook/prophet — what does it do?
```

```
@codewiki What code patterns are used in the routing module of pallets/flask?
```

```
@codewiki Analyse the error handling approach in fastapi/fastapi
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **CodeWiki Code Review** via the `agent` tool |
| 2 | Reviewer calls `codewiki_search_wiki` to find relevant code documentation |
| 3 | Reviewer calls `codewiki_read_contents` for detailed section content |
| 4 | Reviewer provides code-level analysis with citations |

### Validation

- [ ] Master delegates to **CodeWiki Code Review**, not Researcher
- [ ] Reviewer focuses on code structure, patterns, and implementation details
- [ ] Response references specific modules, classes, or functions
- [ ] No hallucinated code — all content sourced from CodeWiki

---

## 3. CodeWiki Architecture Explorer (System Design)

**Routing trigger**: "architecture", "design", "how is X structured", "component hierarchy".

### Prompts

```
@codewiki Explain the overall architecture of facebook/react
```

```
@codewiki How is the plugin system architected in vitejs/vite?
```

```
@codewiki Describe the component hierarchy and data flow in vuejs/core
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **CodeWiki Architecture Explorer** via the `agent` tool |
| 2 | Explorer calls `codewiki_read_structure` to map the documentation tree |
| 3 | Explorer calls `codewiki_read_contents` for architecture-related sections |
| 4 | Explorer produces a structured architecture overview |

### Validation

- [ ] Master delegates to **CodeWiki Architecture Explorer**
- [ ] Response covers high-level design (layers, components, data flow)
- [ ] Includes or references diagrams / structural breakdowns from CodeWiki
- [ ] Does not devolve into code-level details (that's the Reviewer's job)

---

## 4. CodeWiki Comparison (Multi-Repo)

**Routing trigger**: "compare", "vs", "difference between", "X or Y".

### Prompts

```
@codewiki Compare fastapi/fastapi vs pallets/flask — architecture, performance, and developer experience
```

```
@codewiki Compare facebook/react vs vuejs/core in terms of rendering strategy
```

```
@codewiki What are the differences between expressjs/express and koajs/koa?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master spawns **CodeWiki Comparison** via the `agent` tool |
| 2 | Comparison agent calls CodeWiki tools for **each** repo independently |
| 3 | Agent builds a side-by-side analysis from real documentation |
| 4 | Agent produces a structured comparison table or narrative |

### Validation

- [ ] Master delegates to **CodeWiki Comparison**, not Researcher
- [ ] Agent fetches documentation from **both** repos (not just one)
- [ ] Comparison is grounded in CodeWiki content, not generic knowledge
- [ ] Response includes a structured comparison (table, bullet list, or sections)

---

## 5. Request Indexing (Unindexed Repo — Master Handles Directly)

**Routing trigger**: Repo that returns `NOT_INDEXED` from `codewiki_list_topics`.

### Prompts

```
@codewiki Check if Snowflake-Labs/agent-world-model is available on CodeWiki
```

```
@codewiki What does CodeWiki have for some-org/obscure-repo?
```

### Expected Behaviour

| Step | What should happen |
|------|--------------------|
| 1 | Master calls `codewiki_list_topics` directly (it has this tool) |
| 2 | Tool returns `NOT_INDEXED` error |
| 3 | Master calls `codewiki_request_indexing` to submit the repo |
| 4 | Master reports the indexing request to the user |

### Validation

- [ ] Master handles this **directly** (no subagent needed)
- [ ] `codewiki_list_topics` is called first to check availability
- [ ] `codewiki_request_indexing` is called after NOT_INDEXED detection
- [ ] User is informed the repo has been submitted for indexing

---

## Quick Reference: Routing Rules

| User intent | Subagent | Key signal words |
|-------------|----------|-----------------|
| General exploration | CodeWiki Researcher | "what is", "explain", "tell me about", "overview" |
| Code analysis | CodeWiki Code Review | "review", "analyse", "module", "function", "code" |
| System design | CodeWiki Architecture Explorer | "architecture", "design", "structure", "hierarchy" |
| Multi-repo comparison | CodeWiki Comparison | "compare", "vs", "difference", "or" |
| Unindexed repo | *(master directly)* | Any repo returning NOT_INDEXED |

---

## Alternative Repos for Testing

If a repo is too large or slow, try these:

```
# Small SDK — fast wiki generation
anthropics/anthropic-sdk-python

# Medium framework
fastapi/fastapi

# Microsoft tooling
microsoft/vscode-copilot-chat
```
