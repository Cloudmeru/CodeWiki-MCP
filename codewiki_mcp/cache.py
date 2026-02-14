"""In-memory caching layer for CodeWiki page fetches.

Uses cachetools TTLCache to avoid hitting CodeWiki for every request.
Wiki pages are updated infrequently (on PR merges), making caching very effective.
"""

from __future__ import annotations

import logging
from typing import Any

from cachetools import TTLCache

from . import config

logger = logging.getLogger("CodeWiki")

# ---------------------------------------------------------------------------
# Page cache — keyed by URL, TTL from config
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


def invalidate(url: str) -> None:
    """Remove *url* from cache."""
    _page_cache.pop(url, None)


def clear_cache() -> None:
    """Flush the entire page cache."""
    _page_cache.clear()
    logger.debug("Page cache cleared")


def cache_stats() -> dict[str, Any]:
    """Return cache statistics."""
    return {
        "current_size": len(_page_cache),
        "max_size": _page_cache.maxsize,
        "ttl_seconds": int(_page_cache.ttl),
    }
