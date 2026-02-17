"""Repo keyword resolver — resolves product names to owner/repo via CodeWiki search.

When a user provides a bare keyword like "vue", "react", or "openclaw" instead
of a proper owner/repo or full URL, this module searches CodeWiki's search page
(https://codewiki.google/search?q=KEYWORD) and picks the most appropriate repo.

Selection heuristics:
1. Exact owner match (keyword == owner) → pick repo with most stars
2. Exact repo-name match (keyword == repo) → pick repo with most stars
3. Otherwise → pick the first result (highest stars, CodeWiki's default sort)

Results are cached for 30 minutes to avoid redundant Playwright calls.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from dataclasses import dataclass

from . import config
from .browser import _get_browser, run_in_browser_loop
from .stealth import apply_stealth_scripts, stealth_context_options

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
