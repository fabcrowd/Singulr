"""In-memory sliding-window rate limiter keyed by client IP hash."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from singulr.services.hashing import hash_ip


class SlidingWindowRateLimiter:
    """Thread-safe per-key request limiter over a rolling window."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        """Configure max requests per window for each key."""
        self._limit = limit
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """Return True when the key is under the configured limit."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True

    def reset(self) -> None:
        """Clear all tracked keys (used in tests)."""
        with self._lock:
            self._events.clear()


_verify_limiter: SlidingWindowRateLimiter | None = None
_precheck_token_limiter: SlidingWindowRateLimiter | None = None


def get_verify_limiter(limit_per_minute: int) -> SlidingWindowRateLimiter:
    """Return process-wide verify endpoint limiter."""
    global _verify_limiter
    if _verify_limiter is None or _verify_limiter._limit != limit_per_minute:
        _verify_limiter = SlidingWindowRateLimiter(limit_per_minute)
    return _verify_limiter


def allow_verify_request(client_ip: str, *, limit_per_minute: int) -> bool:
    """Check whether a verify API call from client_ip is allowed."""
    key = hash_ip(client_ip)
    return get_verify_limiter(limit_per_minute).allow(key)


def reset_verify_limiter() -> None:
    """Reset verify limiter state (tests only)."""
    if _verify_limiter is not None:
        _verify_limiter.reset()
    if _precheck_token_limiter is not None:
        _precheck_token_limiter.reset()


def get_precheck_token_limiter(limit_per_minute: int) -> SlidingWindowRateLimiter:
    """Return process-wide per-token precheck limiter."""
    global _precheck_token_limiter
    if _precheck_token_limiter is None or _precheck_token_limiter._limit != limit_per_minute:
        _precheck_token_limiter = SlidingWindowRateLimiter(limit_per_minute)
    return _precheck_token_limiter


def allow_precheck_for_token(token: str, *, limit_per_minute: int) -> bool:
    """Check whether another precheck for this verification token is allowed."""
    return get_precheck_token_limiter(limit_per_minute).allow(token)
