"""Repo keyword resolver — resolves product names to owner/repo via CodeWiki search.

When a user provides a bare keyword like "vue", "react", or "openclaw" instead
of a proper owner/repo or full URL, this module searches CodeWiki's search page
(https://codewiki.google/search?q=KEYWORD) and picks the most appropriate repo.

**Disambiguation via MCP Elicitation** (v1.2.0+):
When multiple plausible repos match a keyword, the resolver presents an
interactive selection prompt to the user via the MCP Elicitation protocol
(spec 2025-06-18).  VS Code 0.29+ supports this natively.

**GitHub API fallback** (v1.3.0+):
When CodeWiki search returns 0 results (typo, misspelling, niche repo),
the resolver falls back to the GitHub REST API
(``api.github.com/search/repositories``) which supports fuzzy matching.
This handles typos like "veu" → "vue" or unknown repos not in CodeWiki.

Fallback heuristics (when elicitation is unavailable):
1. Exact owner match (keyword == owner) → pick repo with most stars
2. Exact repo-name match (keyword == repo) → pick repo with most stars
3. Otherwise → pick the first result (highest stars, CodeWiki's default sort)

Results are cached for 30 minutes to avoid redundant calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from . import config
from .browser import _get_browser, run_in_browser_loop
from .stealth import apply_stealth_scripts, stealth_context_options

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

logger = logging.getLogger("CodeWiki")

# ---------------------------------------------------------------------------
# Keyword detection — single word (no slash, no dots in domain position)
# ---------------------------------------------------------------------------
KEYWORD_PATTERN = re.compile(r"^[\w][\w.\-]*$")


def is_bare_keyword(value: str) -> bool:
    """Return True if *value* is a bare product keyword (not owner/repo, not URL)."""
    v = value.strip()
    if not v or "/" in v or v.startswith("http"):
        return False
    return bool(KEYWORD_PATTERN.match(v))


# ---------------------------------------------------------------------------
# Search result model
# ---------------------------------------------------------------------------
@dataclass
class SearchResult:
    """A single repo result from CodeWiki's search page."""

    owner: str
    repo: str
    description: str
    stars: int  # 0 if not parseable
    codewiki_url: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


# ---------------------------------------------------------------------------
# In-memory cache for resolved keywords (TTL managed by cachetools)
# ---------------------------------------------------------------------------
from cachetools import TTLCache  # noqa: E402

_resolve_cache: TTLCache[str, list[SearchResult]] = TTLCache(
    maxsize=50,
    ttl=1800,  # 30 minutes
)


# ---------------------------------------------------------------------------
# Parse star count from text like "209.9k", "1.3k", "52", ""
# ---------------------------------------------------------------------------
def _parse_stars(text: str) -> int:
    """Parse a star-count string like '209.9k' into an integer."""
    text = text.strip().lower().replace(",", "")
    if not text:
        return 0
    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        elif text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        return int(float(text))
    except (ValueError, IndexError):
        return 0


# ---------------------------------------------------------------------------
# Playwright: scrape search results
# ---------------------------------------------------------------------------
async def _scrape_search_results(keyword: str) -> list[SearchResult]:
    """Navigate to CodeWiki search and extract repo results."""
    search_url = (
        f"{config.CODEWIKI_BASE_URL}/search"
        f"?q={urllib.parse.quote(keyword, safe='')}"
    )

    browser = await _get_browser()
    ctx_opts = stealth_context_options()
    ctx_opts["user_agent"] = config.USER_AGENT
    context = await browser.new_context(**ctx_opts)
    page = await context.new_page()
    await apply_stealth_scripts(page)

    try:
        logger.info("resolver: searching CodeWiki for keyword '%s' → %s", keyword, search_url)
        await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=config.PAGE_LOAD_TIMEOUT_SECONDS * 1000,
        )
        await asyncio.sleep(config.JS_LOAD_DELAY_SECONDS)

        # Wait for search results to render
        try:
            await page.wait_for_selector("a[href*='/github.com/']", timeout=10_000)
        except Exception:
            logger.warning("resolver: no search results found for '%s'", keyword)
            return []

        # Extract all result links that point to CodeWiki repo pages
        # Pattern: <a href="https://codewiki.google/github.com/owner/repo">
        results: list[SearchResult] = []
        links = await page.query_selector_all("a[href*='/github.com/']")

        for link in links:
            try:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()

                # Parse owner/repo from href
                # href like: https://codewiki.google/github.com/vuejs/vue
                # or relative: /github.com/vuejs/vue
                match = re.search(r"github\.com/([\w.\-]+)/([\w.\-]+)", href)
                if not match:
                    continue

                owner = match.group(1)
                repo = match.group(2)

                # Skip duplicates
                if any(r.owner == owner and r.repo == repo for r in results):
                    continue

                # Parse star count — usually the last number-like token in text
                # Text looks like: "vuejs vue vuejs This is the repo for Vue 2... 209.9k"
                stars = 0
                star_match = re.search(r"([\d,.]+[kKmM]?)\s*$", text)
                if star_match:
                    stars = _parse_stars(star_match.group(1))

                # Description: the middle text between owner/repo names and star count
                description = text

                results.append(SearchResult(
                    owner=owner,
                    repo=repo,
                    description=description[:200],
                    stars=stars,
                    codewiki_url=href if href.startswith("http") else f"{config.CODEWIKI_BASE_URL}{href}",
                ))
            except Exception as exc:
                logger.debug("resolver: failed to parse a search result link: %s", exc)
                continue

        logger.info("resolver: found %d results for '%s'", len(results), keyword)
        return results

    except Exception as exc:
        logger.error("resolver: search scrape failed for '%s': %s", keyword, exc)
        return []
    finally:
        await page.close()
        await context.close()


def _fetch_search_results(keyword: str) -> list[SearchResult]:
    """Synchronous wrapper: scrape CodeWiki search results for *keyword*."""
    cached = _resolve_cache.get(keyword.lower())
    if cached is not None:
        logger.debug("resolver: cache HIT for keyword '%s' (%d results)", keyword, len(cached))
        return cached

    try:
        results = run_in_browser_loop(_scrape_search_results(keyword))
    except asyncio.TimeoutError:
        logger.warning("resolver: timed out searching for '%s'", keyword)
        results = []
    except Exception as exc:
        logger.warning("resolver: error searching for '%s': %s", keyword, exc)
        results = []

    _resolve_cache[keyword.lower()] = results
    return results


# ---------------------------------------------------------------------------
# GitHub API fallback — handles typos, misspellings, niche repos
# ---------------------------------------------------------------------------
GITHUB_API_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_API_TIMEOUT = 10  # seconds

_github_cache: TTLCache[str, list[SearchResult]] = TTLCache(
    maxsize=50,
    ttl=1800,  # 30 minutes
)


def _github_search(keyword: str, max_results: int = 10) -> list[SearchResult]:
    """Search GitHub REST API for repositories matching *keyword*.

    GitHub's search supports fuzzy/typo matching — e.g. "veu" finds "vue".
    Uses ``urllib.request`` (stdlib) so no extra dependencies needed.

    Returns a list of SearchResult (same shape as CodeWiki results)
    so the elicitation and selection logic is reusable.
    """
    cached = _github_cache.get(keyword.lower())
    if cached is not None:
        logger.debug("resolver: GitHub cache HIT for '%s' (%d results)", keyword, len(cached))
        return cached

    query = urllib.parse.urlencode({
        "q": keyword,
        "sort": "stars",
        "order": "desc",
        "per_page": str(max_results),
    })
    url = f"{GITHUB_API_SEARCH_URL}?{query}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CodeWiki-MCP/1.3.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=GITHUB_API_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())

        results: list[SearchResult] = []
        for item in data.get("items", [])[:max_results]:
            full_name = item.get("full_name", "")
            if "/" not in full_name:
                continue
            owner, repo = full_name.split("/", 1)
            results.append(SearchResult(
                owner=owner,
                repo=repo,
                description=(item.get("description") or "")[:200],
                stars=item.get("stargazers_count", 0),
                codewiki_url=f"{config.CODEWIKI_BASE_URL}/github.com/{full_name}",
            ))

        logger.info(
            "resolver: GitHub API found %d results for '%s'",
            len(results), keyword,
        )
        _github_cache[keyword.lower()] = results
        return results

    except Exception as exc:
        logger.warning("resolver: GitHub API search failed for '%s': %s", keyword, exc)
        _github_cache[keyword.lower()] = []
        return []


# ---------------------------------------------------------------------------
# Selection heuristics — pick the best repo from search results
# ---------------------------------------------------------------------------
def _select_best_match(keyword: str, results: list[SearchResult]) -> SearchResult | None:
    """Pick the most appropriate repo for the given keyword.

    Heuristics (in priority order):
    1. Exact owner match where repo == owner (canonical repo)
       e.g., keyword "vue" → vuejs/vue (owner "vuejs" contains "vue", repo IS "vue")
       e.g., keyword "openclaw" → openclaw/openclaw (owner == repo == keyword)
    2. Exact repo-name match → pick the one with most stars
    3. Owner name contains keyword → pick the one with most stars
    4. First result (CodeWiki sorts by relevance/stars)
    """
    kw = keyword.lower().strip()
    if not results:
        return None

    # --- Heuristic 1: Canonical repo (owner matches keyword, repo matches keyword) ---
    # e.g., "openclaw" → openclaw/openclaw
    canonical = [r for r in results if r.owner.lower() == kw and r.repo.lower() == kw]
    if canonical:
        return max(canonical, key=lambda r: r.stars)

    # --- Heuristic 2: Repo name exactly matches keyword ---
    # e.g., "vue" → vuejs/vue (repo name is "vue")
    exact_repo = [r for r in results if r.repo.lower() == kw]
    if exact_repo:
        return max(exact_repo, key=lambda r: r.stars)

    # --- Heuristic 3: Owner contains keyword + repo looks primary ---
    # e.g., "react" → facebook/react
    # Look for repos where the owner name contains the keyword
    owner_match = [r for r in results if kw in r.owner.lower()]
    if owner_match:
        # Prefer repo where repo name also matches keyword
        owner_and_repo = [r for r in owner_match if r.repo.lower() == kw]
        if owner_and_repo:
            return max(owner_and_repo, key=lambda r: r.stars)
        # Otherwise pick the highest-star owner match
        return max(owner_match, key=lambda r: r.stars)

    # --- Heuristic 4: Repo name contains keyword ---
    repo_contains = [r for r in results if kw in r.repo.lower()]
    if repo_contains:
        return max(repo_contains, key=lambda r: r.stars)

    # --- Fallback: first result (highest stars by CodeWiki's sort) ---
    return results[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def resolve_keyword(keyword: str) -> tuple[str | None, list[SearchResult]]:
    """Resolve a bare keyword to an owner/repo string.

    Returns:
        (resolved_owner_repo, all_results)
        - resolved_owner_repo: "owner/repo" string if found, None if no results
        - all_results: full list of SearchResult for transparency
    """
    results = _fetch_search_results(keyword)
    if not results:
        return None, []

    best = _select_best_match(keyword, results)
    if best is None:
        return None, results

    logger.info(
        "resolver: keyword '%s' → %s (%d★, %d candidates)",
        keyword, best.full_name, best.stars, len(results),
    )
    return best.full_name, results


# ---------------------------------------------------------------------------
# MCP Elicitation — interactive disambiguation (v1.2.0+)
# ---------------------------------------------------------------------------
MAX_ELICITATION_CHOICES = 6  # max options to show user


def _format_stars(stars: int) -> str:
    """Format star count for display (e.g. 209900 → '209.9k')."""
    if stars >= 1_000_000:
        return f"{stars / 1_000_000:.1f}M"
    if stars >= 1000:
        return f"{stars / 1000:.1f}k"
    return str(stars)


def _has_canonical_match(keyword: str, results: list[SearchResult]) -> SearchResult | None:
    """Return repo where keyword == owner == repo (e.g. 'openclaw' → openclaw/openclaw)."""
    kw = keyword.lower().strip()
    for r in results:
        if r.owner.lower() == kw and r.repo.lower() == kw:
            return r
    return None


def build_repo_choice_model(results: list[SearchResult]) -> type[BaseModel]:
    """Create a dynamic Pydantic model with Literal enum for MCP elicitation.

    Produces a JSON schema with ``"enum"`` values that VS Code renders
    as a selection list in the chat UI.
    """
    top = results[:MAX_ELICITATION_CHOICES]
    options = tuple(r.full_name for r in top)
    literal_type = Literal[options]  # type: ignore[valid-type]

    # Build rich descriptions for the enum help text
    lines: list[str] = []
    for r in top:
        desc = r.full_name
        if r.stars:
            desc += f" ({_format_stars(r.stars)}★)"
        lines.append(f"• {desc}")

    class RepoChoice(BaseModel):
        """User's repository selection from disambiguation prompt."""

        selected_repo: literal_type = Field(  # type: ignore[valid-type]
            description="Select the repository:\n" + "\n".join(lines),
        )

    return RepoChoice


async def _elicit_repo_choice(
    keyword: str,
    results: list[SearchResult],
    ctx: Context,
) -> str | None:
    """Ask the user to pick a repo via MCP elicitation.

    Returns the selected ``owner/repo`` or ``None`` if user declines/cancels.
    """
    Model = build_repo_choice_model(results)  # noqa: N806

    # Build a descriptive message for the elicitation prompt
    top = results[:MAX_ELICITATION_CHOICES]
    lines = [f'Multiple repositories match **"{keyword}"**.', ""]
    for i, r in enumerate(top, 1):
        star_str = f" ({_format_stars(r.stars)}★)" if r.stars else ""
        lines.append(f"{i}. **{r.full_name}**{star_str}")
    lines.append("")
    lines.append("Which repository do you want to explore?")
    message = "\n".join(lines)

    result = await ctx.elicit(message=message, schema=Model)

    if result.action == "accept" and result.data is not None:
        selected: str = result.data.selected_repo  # type: ignore[attr-defined]
        logger.info("resolver: user selected '%s' for keyword '%s'", selected, keyword)
        return selected

    logger.info("resolver: user %s elicitation for keyword '%s'", result.action, keyword)
    return None


def resolve_keyword_interactive(
    keyword: str,
    ctx: Context | None = None,
) -> tuple[str | None, list[SearchResult]]:
    """Resolve a bare keyword with interactive disambiguation.

    This is the primary entry point for tools.  It:
    1. Fetches search results from CodeWiki (cached for 30 min).
    2. If CodeWiki returns 0 results → falls back to GitHub API search
       (handles typos, misspellings, niche repos).
    3. Auto-selects if only 1 result or canonical match.
    4. Tries MCP elicitation for ambiguous cases (when *ctx* is available).
    5. Falls back to heuristic selection if elicitation fails or is unsupported.

    Returns:
        (selected_owner_repo, all_results) — same shape as ``resolve_keyword()``.
    """
    results = _fetch_search_results(keyword)

    # --- GitHub API fallback for typos / not found on CodeWiki ---
    source = "codewiki"
    if not results:
        logger.info(
            "resolver: no CodeWiki results for '%s', trying GitHub API fallback",
            keyword,
        )
        results = _github_search(keyword)
        source = "github"
        if not results:
            return None, []

    # --- Single result → auto-select ---
    if len(results) == 1:
        logger.info(
            "resolver: single result (%s) for '%s' → %s",
            source, keyword, results[0].full_name,
        )
        return results[0].full_name, results

    # --- Canonical match (keyword == owner == repo) → auto-select ---
    canonical = _has_canonical_match(keyword, results)
    if canonical:
        logger.info(
            "resolver: canonical match (%s) for '%s' → %s (%d★)",
            source, keyword, canonical.full_name, canonical.stars,
        )
        return canonical.full_name, results

    # --- Multiple ambiguous results → try elicitation ---
    if ctx is not None:
        try:
            import anyio.from_thread  # noqa: E402

            selected = anyio.from_thread.run(_elicit_repo_choice, keyword, results, ctx)
            if selected:
                return selected, results
            # User declined/cancelled → fall through to heuristic
            logger.info("resolver: elicitation declined for '%s', using heuristic", keyword)
        except Exception as exc:
            logger.warning(
                "resolver: elicitation failed for '%s' (client may not support it): %s",
                keyword,
                exc,
            )
            # Fall through to heuristic selection

    # --- Fallback: heuristic selection ---
    best = _select_best_match(keyword, results)
    if best is None:
        return None, results

    logger.info(
        "resolver: heuristic fallback '%s' → %s (%d★, %d candidates)",
        keyword, best.full_name, best.stars, len(results),
    )
    return best.full_name, results
