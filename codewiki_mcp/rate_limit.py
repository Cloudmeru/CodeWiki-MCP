"""Per-repo sliding-window rate limiter for CodeWiki MCP tools.

Prevents runaway agent loops from hammering CodeWiki with the same
request hundreds of times.  Each repo URL gets its own counter that
tracks calls within a configurable window (default: 10 calls / 60 s).

When the limit is exceeded the tool returns a clear error response
so the agent knows to stop retrying.

Thread-safe: uses a ``threading.Lock`` to guard the counter state.
"""

from __future__ import annotations

import logging
import threading
import time

from . import config

logger = logging.getLogger("CodeWiki")

# ---------------------------------------------------------------------------
# Per-key sliding window
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_windows: dict[str, list[float]] = {}


def check_rate_limit(key: str) -> bool:
    """Return ``True`` if the request is allowed, ``False`` if rate-limited.

    Each call records a timestamp for *key*.  Timestamps older than
    ``RATE_LIMIT_WINDOW_SECONDS`` are pruned.  If the remaining count
    exceeds ``RATE_LIMIT_MAX_CALLS``, the request is rejected.
    """
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    max_calls = config.RATE_LIMIT_MAX_CALLS

    with _lock:
        timestamps = _windows.setdefault(key, [])
        # Prune expired entries
        cutoff = now - window
        _windows[key] = [t for t in timestamps if t > cutoff]
        timestamps = _windows[key]

        if len(timestamps) >= max_calls:
            logger.warning(
                "Rate limit exceeded for %s (%d calls in %ds window)",
                key,
                len(timestamps),
                window,
            )
            return False

        timestamps.append(now)
        return True


def rate_limit_remaining(key: str) -> int:
    """Return how many calls remain in the current window for *key*."""
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    max_calls = config.RATE_LIMIT_MAX_CALLS

    with _lock:
        timestamps = _windows.get(key, [])
        cutoff = now - window
        active = [t for t in timestamps if t > cutoff]
        return max(0, max_calls - len(active))


def reset_rate_limits() -> None:
    """Clear all rate-limit state (mainly for testing)."""
    with _lock:
        _windows.clear()
