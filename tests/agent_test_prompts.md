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

## Agent Configuration Reference

Current YAML frontmatter for each agent (must match `.github/agents/` files):

### Master Orchestrator (`codewiki.agent.md`)

```yaml
name: CodeWiki
description: Master agent that routes your request to the right CodeWiki specialist
model: GPT-5.3-Codex
tools:
  [read, agent, codewiki-mcp/*]
agents:
  [CodeWiki Researcher, CodeWiki Code Review, CodeWiki Architecture Explorer, CodeWiki Comparison, CodeWiki Synthesizer]
```

> **⚠️ Model:** The master must use a **1× credit model** like `GPT-5.3-Codex`.
> Free/low-tier models (GPT-5 mini) produce inconsistent routing, truncated
> results, and skipped delegation.
>
> **Why `codewiki-mcp/*` on the master?** The master must declare MCP tools
> so they are exposed to subagents when spawned. The master itself still acts
> as a router — it delegates via `agent` and does not call CodeWiki tools directly.

### Subagents (4 use GPT-5 mini, 1 uses GPT-5.3-Codex)

```yaml
# Researcher, Code Review, Architecture Explorer, Comparison:
model: GPT-5 mini
user-invokable: false
tools:
  [read, codewiki-mcp/*]

# Synthesizer (needs stronger reasoning for multi-repo integration):
model: GPT-5.3-Codex
user-invokable: false
tools:
  [read, codewiki-mcp/*]
```

| Agent File | Name | Specialty |
|-----------|------|-----------|
| `codewiki-researcher.agent.md` | CodeWiki Researcher | General exploration |
| `codewiki-reviewer.agent.md` | CodeWiki Code Review | Module/function analysis |
| `codewiki-architect.agent.md` | CodeWiki Architecture Explorer | System design |
| `codewiki-comparison.agent.md` | CodeWiki Comparison | Multi-repo comparison |
| `codewiki-synthesizer.agent.md` | CodeWiki Synthesizer | Combine parts from multiple repos |

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
- [ ] Master presents the **full** subagent response (not a brief summary)

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
- [ ] Master presents the **full** subagent response (not a brief summary)

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
- [ ] Master presents the **full** subagent response (not a brief summary)

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
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 5. Request Indexing (Unindexed Repo — Subagent Handles It)

**Routing trigger**: Repo that returns `NOT_INDEXED` from any CodeWiki tool.

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
| 1 | Master classifies this as a general exploration request |
| 2 | Master spawns **CodeWiki Researcher** via the `agent` tool |
| 3 | Researcher calls a CodeWiki tool and gets `NOT_INDEXED` error |
| 4 | Researcher calls `codewiki_request_indexing` to submit the repo |
| 5 | Researcher reports back; Master presents the full result to user |

### Validation

- [ ] Master does **not** call any MCP tools directly (it has none)
- [ ] A subagent detects `NOT_INDEXED` and calls `codewiki_request_indexing`
- [ ] User is informed the repo has been submitted for indexing
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## 6. CodeWiki Synthesizer (Multi-Repo Solution Building)

**Routing trigger**: User wants to BUILD something new by combining parts from multiple repos. Distinct from Comparison which evaluates/contrasts.

### Prompts

```
@codewiki I want to build an API server that uses the routing system from pallets/flask and the async handling from fastapi/fastapi. Help me design it.
```

```
@codewiki Take the plugin architecture from vitejs/vite and the component model from vuejs/core — design a new framework that combines both.
```

```
@codewiki Combine the authentication approach from supabase/supabase with the event pipeline from apache/kafka into a real-time auth notification system.
```

### Expected Behaviour

| Step | What should happen |
|------|-----------------------|
| 1 | Master detects synthesis intent ("build", "combine", "take X from A and Y from B") |
| 2 | Master spawns **CodeWiki Synthesizer** via the `agent` tool |
| 3 | Synthesizer researches each repo using CodeWiki tools (read_structure, read_contents, search_wiki) |
| 4 | Synthesizer extracts the specific parts the user requested from each repo |
| 5 | Synthesizer identifies cross-repo conflicts and proposes adapters |
| 6 | Synthesizer delivers a blueprint: architecture diagram, directory structure, integration code, implementation guide |

### Validation

- [ ] Master delegates to **CodeWiki Synthesizer**, not Comparison
- [ ] Synthesizer fetches documentation from **all** mentioned repos
- [ ] Response includes a **Parts Extracted** table citing source repos
- [ ] Response includes **Compatibility Analysis** (conflicts + resolutions)
- [ ] Response includes **Integration Architecture** (Mermaid diagram or description)
- [ ] Response includes **Directory Structure** for the new project
- [ ] Response includes **Implementation Guide** with actionable steps
- [ ] All content is grounded in CodeWiki data, not generic knowledge
- [ ] Master presents the **full** subagent response (not a brief summary)

---

## Quick Reference: Routing Rules

| User intent | Subagent | Key signal words |
|-------------|----------|-----------------|
| General exploration | CodeWiki Researcher | "what is", "explain", "tell me about", "overview" |
| Code analysis | CodeWiki Code Review | "review", "analyse", "module", "function", "code" |
| System design | CodeWiki Architecture Explorer | "architecture", "design", "structure", "hierarchy" |
| Multi-repo comparison | CodeWiki Comparison | "compare", "vs", "difference", "or" |
| Multi-repo synthesis | CodeWiki Synthesizer | "combine", "merge", "build using", "take X from A and Y from B" |
| Unindexed repo | CodeWiki Researcher | Subagent detects NOT_INDEXED and calls `codewiki_request_indexing` |

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
