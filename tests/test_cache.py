"""Tests for the in-memory TTL cache layer."""

from __future__ import annotations

from codewiki_mcp.cache import (
    cache_stats,
    clear_cache,
    get_cached_page,
    invalidate,
    set_cached_page,
)


class TestPageCache:
    def setup_method(self):
        clear_cache()

    def test_miss_returns_none(self):
        assert get_cached_page("https://example.com/page") is None

    def test_set_and_get(self):
        url = "https://codewiki.google/github.com/owner/repo"
        html = "<html><body>Hello</body></html>"
        set_cached_page(url, html)
        assert get_cached_page(url) == html

    def test_invalidate(self):
        url = "https://codewiki.google/github.com/owner/repo"
        set_cached_page(url, "<html>test</html>")
        assert get_cached_page(url) is not None
        invalidate(url)
        assert get_cached_page(url) is None

    def test_invalidate_nonexistent_is_noop(self):
        invalidate("https://no-such-url.com")  # should not raise

    def test_clear_cache(self):
        set_cached_page("https://a.com", "aaa")
        set_cached_page("https://b.com", "bbb")
        clear_cache()
        assert get_cached_page("https://a.com") is None
        assert get_cached_page("https://b.com") is None

    def test_cache_stats(self):
        clear_cache()
        stats = cache_stats()
        assert stats["current_size"] == 0
        assert stats["max_size"] > 0
        assert stats["ttl_seconds"] > 0

        set_cached_page("https://x.com", "x")
        stats = cache_stats()
        assert stats["current_size"] == 1

    def test_overwrite_value(self):
        url = "https://test.com/page"
        set_cached_page(url, "v1")
        assert get_cached_page(url) == "v1"
        set_cached_page(url, "v2")
        assert get_cached_page(url) == "v2"
