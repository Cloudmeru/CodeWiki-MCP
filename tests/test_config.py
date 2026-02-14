"""Tests for environment-variable-driven configuration."""

from __future__ import annotations

import importlib
import os


class TestConfig:
    def test_default_values(self):
        from codewiki_mcp import config

        assert config.HARD_TIMEOUT_SECONDS == 60
        assert config.MAX_RETRIES == 2
        assert config.RESPONSE_MAX_CHARS == 30000
        assert config.CODEWIKI_BASE_URL == "https://codewiki.google"

    def test_httpx_defaults(self):
        from codewiki_mcp import config

        assert config.HTTPX_TIMEOUT_SECONDS == 30

    def test_cache_defaults(self):
        from codewiki_mcp import config

        assert config.CACHE_TTL_SECONDS == 300
        assert config.CACHE_MAX_SIZE == 50

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CODEWIKI_HARD_TIMEOUT", "120")
        monkeypatch.setenv("CODEWIKI_MAX_RETRIES", "5")
        monkeypatch.setenv("CODEWIKI_VERBOSE", "true")
        monkeypatch.setenv("CODEWIKI_BASE_URL", "https://custom.url")

        # Force reimport to pick up new env vars
        from codewiki_mcp import config

        importlib.reload(config)

        assert config.HARD_TIMEOUT_SECONDS == 120
        assert config.MAX_RETRIES == 5
        assert config.VERBOSE is True
        assert config.CODEWIKI_BASE_URL == "https://custom.url"

        # Reset
        importlib.reload(config)

    def test_httpx_env_override(self, monkeypatch):
        monkeypatch.setenv("CODEWIKI_HTTPX_TIMEOUT", "60")

        from codewiki_mcp import config

        importlib.reload(config)

        assert config.HTTPX_TIMEOUT_SECONDS == 60

        importlib.reload(config)

    def test_cache_env_override(self, monkeypatch):
        monkeypatch.setenv("CODEWIKI_CACHE_TTL", "600")
        monkeypatch.setenv("CODEWIKI_CACHE_MAX_SIZE", "100")

        from codewiki_mcp import config

        importlib.reload(config)

        assert config.CACHE_TTL_SECONDS == 600
        assert config.CACHE_MAX_SIZE == 100

        importlib.reload(config)

    def test_invalid_env_uses_default(self, monkeypatch):
        monkeypatch.setenv("CODEWIKI_HARD_TIMEOUT", "not_a_number")

        from codewiki_mcp import config

        importlib.reload(config)
        assert config.HARD_TIMEOUT_SECONDS == 60
        importlib.reload(config)

    def test_selectors_populated(self):
        from codewiki_mcp import config

        assert len(config.CHAT_INPUT_SELECTORS) > 0
        assert len(config.SUBMIT_BUTTON_SELECTORS) > 0
        assert len(config.RESPONSE_ELEMENT_SELECTORS) > 0
