"""In-memory caching layer for CodeWiki page fetches.

Uses cachetools TTLCache to avoid hitting CodeWiki for every request.
Wiki pages are updated infrequently (on PR merges), making caching very effective.

Three caches:
- **HTML cache** — raw rendered HTML keyed by URL
- **Parsed cache** — ``WikiPage`` objects keyed by repo URL (avoids re-parsing)
- **Search cache** — search responses keyed by ``repo_url::query``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache

from . import config

if TYPE_CHECKING:
    from .parser import WikiPage  # avoid circular import at runtime

logger = logging.getLogger("CodeWiki")

# ---------------------------------------------------------------------------
# HTML page cache — keyed by rendered URL, TTL from config
# ---------------------------------------------------------------------------
_page_cache: TTLCache[str, str] = TTLCache(
    maxsize=config.CACHE_MAX_SIZE,
    ttl=config.CACHE_TTL_SECONDS,
)


def get_cached_page(url: str) -> str | None:
    """Return cached HTML for *url*, or None if not cached / expired."""
    result = _page_cache.get(url)
    if result is not None:
        logger.debug("Cache HIT for %s (%d chars)", url, len(result))
    else:
        logger.debug("Cache MISS for %s", url)
    return result


def set_cached_page(url: str, html: str) -> None:
    """Store *html* in the page cache keyed by *url*."""
    _page_cache[url] = html
    logger.debug("Cached %s (%d chars)", url, len(html))


# ---------------------------------------------------------------------------
# Parsed WikiPage cache — avoids re-parsing the same HTML
# ---------------------------------------------------------------------------
_parsed_cache: TTLCache = TTLCache(
    maxsize=config.PARSED_CACHE_MAX_SIZE,
    ttl=config.CACHE_TTL_SECONDS,
)


def get_cached_wiki_page(repo_url: str) -> Any:
    """Return a cached ``WikiPage`` for *repo_url*, or ``None``."""
    result = _parsed_cache.get(repo_url)
    if result is not None:
        logger.debug("Parsed-cache HIT for %s", repo_url)
    return result


def set_cached_wiki_page(repo_url: str, page: Any) -> None:
    """Cache a parsed ``WikiPage`` keyed by *repo_url*."""
    _parsed_cache[repo_url] = page
    logger.debug("Parsed-cache stored %s", repo_url)


# ---------------------------------------------------------------------------
# Search response cache — avoids re-querying the same question
# ---------------------------------------------------------------------------
_search_cache: TTLCache[str, str] = TTLCache(
    maxsize=config.SEARCH_CACHE_MAX_SIZE,
    ttl=config.SEARCH_CACHE_TTL_SECONDS,
)


def get_cached_search(repo_url: str, query: str) -> str | None:
    """Return a cached search response, or ``None``."""
    key = f"{repo_url}::{query.strip().lower()}"
    result = _search_cache.get(key)
    if result is not None:
        logger.debug("Search-cache HIT for %s :: %s", repo_url, query[:60])
    return result


def set_cached_search(repo_url: str, query: str, response: str) -> None:
    """Cache a search response keyed by *repo_url* + *query*."""
    key = f"{repo_url}::{query.strip().lower()}"
    _search_cache[key] = response
    logger.debug("Search-cache stored %s :: %s", repo_url, query[:60])


# ---------------------------------------------------------------------------
# General-purpose helpers
# ---------------------------------------------------------------------------
def invalidate(url: str) -> None:
    """Remove *url* from the HTML cache."""
    _page_cache.pop(url, None)


def clear_cache() -> None:
    """Flush all caches (HTML + parsed + search)."""
    _page_cache.clear()
    _parsed_cache.clear()
    _search_cache.clear()
    logger.debug("All caches cleared")


def cache_stats() -> dict[str, Any]:
    """Return statistics for all caches."""
    return {
        "html": {
            "current_size": len(_page_cache),
            "max_size": _page_cache.maxsize,
            "ttl_seconds": int(_page_cache.ttl),
        },
        "parsed": {
            "current_size": len(_parsed_cache),
            "max_size": _parsed_cache.maxsize,
            "ttl_seconds": int(_parsed_cache.ttl),
        },
        "search": {
            "current_size": len(_search_cache),
            "max_size": _search_cache.maxsize,
            "ttl_seconds": int(_search_cache.ttl),
        },
    }
