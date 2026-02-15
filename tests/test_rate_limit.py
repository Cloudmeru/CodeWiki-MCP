"""Tests for per-repo sliding-window rate limiter."""

from __future__ import annotations

from codewiki_mcp.rate_limit import (
    check_rate_limit,
    rate_limit_remaining,
    reset_rate_limits,
)


class TestRateLimit:
    def setup_method(self):
        reset_rate_limits()

    def test_allows_under_limit(self):
        """Calls within the limit are all allowed."""
        for _ in range(10):
            assert check_rate_limit("repo-a") is True

    def test_blocks_over_limit(self):
        """The 11th call in the window is rejected."""
        for _ in range(10):
            check_rate_limit("repo-b")
        assert check_rate_limit("repo-b") is False

    def test_different_keys_independent(self):
        """Rate limits are per-key — different repos don't interfere."""
        for _ in range(10):
            check_rate_limit("repo-c")
        # repo-c is exhausted
        assert check_rate_limit("repo-c") is False
        # repo-d is fresh
        assert check_rate_limit("repo-d") is True

    def test_remaining_decreases(self):
        """rate_limit_remaining counts down correctly."""
        assert rate_limit_remaining("repo-e") == 10
        check_rate_limit("repo-e")
        assert rate_limit_remaining("repo-e") == 9
        for _ in range(9):
            check_rate_limit("repo-e")
        assert rate_limit_remaining("repo-e") == 0

    def test_reset_clears_all(self):
        """reset_rate_limits clears all state."""
        for _ in range(10):
            check_rate_limit("repo-f")
        assert check_rate_limit("repo-f") is False
        reset_rate_limits()
        assert check_rate_limit("repo-f") is True
        assert rate_limit_remaining("repo-f") == 9  # one call just made
