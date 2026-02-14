"""Environment-variable-driven configuration for CodeWiki MCP.

All settings have sensible defaults and can be overridden via env vars
(like DeepWiki MCP's DEEPWIKI_MAX_CONCURRENCY / DEEPWIKI_REQUEST_TIMEOUT).
"""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name, "")
    if val.strip():
        try:
            return int(val)
        except ValueError:
            pass
    return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
HARD_TIMEOUT_SECONDS: int = _env_int("CODEWIKI_HARD_TIMEOUT", 60)
PAGE_LOAD_TIMEOUT_SECONDS: int = _env_int("CODEWIKI_PAGE_LOAD_TIMEOUT", 30)
ELEMENT_WAIT_TIMEOUT_SECONDS: int = _env_int("CODEWIKI_ELEMENT_WAIT_TIMEOUT", 20)
RESPONSE_WAIT_TIMEOUT_SECONDS: int = _env_int("CODEWIKI_RESPONSE_WAIT_TIMEOUT", 45)
HTTPX_TIMEOUT_SECONDS: int = _env_int("CODEWIKI_HTTPX_TIMEOUT", 30)

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
MAX_RETRIES: int = _env_int("CODEWIKI_MAX_RETRIES", 2)
RETRY_DELAY_SECONDS: int = _env_int("CODEWIKI_RETRY_DELAY", 3)

# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------
RESPONSE_MAX_CHARS: int = _env_int("CODEWIKI_RESPONSE_MAX_CHARS", 30000)

# ---------------------------------------------------------------------------
# Cache (cachetools TTLCache)
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS: int = _env_int("CODEWIKI_CACHE_TTL", 300)  # 5 minutes
CACHE_MAX_SIZE: int = _env_int("CODEWIKI_CACHE_MAX_SIZE", 50)

# ---------------------------------------------------------------------------
# Playwright chat timing
# ---------------------------------------------------------------------------
RESPONSE_INITIAL_DELAY_SECONDS: int = _env_int("CODEWIKI_RESPONSE_INITIAL_DELAY", 5)
RESPONSE_POLL_INTERVAL_SECONDS: int = _env_int("CODEWIKI_RESPONSE_POLL_INTERVAL", 2)
RESPONSE_STABLE_INTERVAL_SECONDS: int = _env_int("CODEWIKI_RESPONSE_STABLE_INTERVAL", 2)
JS_LOAD_DELAY_SECONDS: int = _env_int("CODEWIKI_JS_LOAD_DELAY", 3)
INPUT_CLEAR_DELAY: float = 0.3
INPUT_TYPE_DELAY: float = 0.5
SUBMIT_DELAY: float = 1.0

# ---------------------------------------------------------------------------
# Content detection
# ---------------------------------------------------------------------------
NEW_CONTENT_THRESHOLD_CHARS: int = 50
FALLBACK_MIN_TEXT_LENGTH: int = 20

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------
VERBOSE: bool = _env_bool("CODEWIKI_VERBOSE", False)

# ---------------------------------------------------------------------------
# Base URL
# ---------------------------------------------------------------------------
CODEWIKI_BASE_URL: str = os.environ.get("CODEWIKI_BASE_URL", "https://codewiki.google")

# ---------------------------------------------------------------------------
# User agent
# ---------------------------------------------------------------------------
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Selectors (for Playwright chat interaction — CodeWiki Angular SPA)
#
# These selectors target the actual CodeWiki SPA elements:
#   <chat class="is-open">
#     <thread>  →  <cdk-virtual-scroll-viewport>  (messages)
#     <new-message-form>  →  <form>  →  <textarea id="message-textarea">
#     <button data-test-id="send-message-button">
# ---------------------------------------------------------------------------
CHAT_ELEMENT_SELECTOR: str = "chat"
CHAT_OPEN_SELECTOR: str = "chat.is-open"
CHAT_TOGGLE_SELECTOR: str = "chat-toggle button"

CHAT_INPUT_SELECTORS: list[str] = [
    "textarea[data-test-id='chat-input']",
    "textarea#message-textarea",
    "textarea[placeholder*='Ask about this repository']",
    "new-message-form textarea",
    "chat textarea",
]

SUBMIT_BUTTON_SELECTORS: list[str] = [
    "button[data-test-id='send-message-button']",
    "button[aria-label='Send message']",
    "new-message-form button[type='submit']",
    "chat .send-button",
]

# Response messages appear inside the <thread> → <cdk-virtual-scroll-viewport>
CHAT_THREAD_SELECTOR: str = "chat thread"
CHAT_SCROLL_VIEWPORT: str = "chat cdk-virtual-scroll-viewport"
CHAT_SCROLL_CONTENT: str = "chat .cdk-virtual-scroll-content-wrapper"

# Individual message elements inside the thread
RESPONSE_ELEMENT_SELECTORS: list[str] = [
    "chat .cdk-virtual-scroll-content-wrapper documentation-markdown",
    "chat .cdk-virtual-scroll-content-wrapper",
    "chat thread",
]

# The empty state has "Hi there!" — we use this to detect pre-response state
CHAT_EMPTY_STATE_SELECTOR: str = "chat .empty-house-container"

UI_ARTIFACTS: list[str] = [
    "content_copy",
    "refresh",
    "thumb_up",
    "thumb_down",
    "arrow_menu_open",
    "Gemini can make mistakes, so double-check it.",
]
