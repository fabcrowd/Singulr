"""Per-channel join request velocity tracker for farm-wave detection."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from singulr.config import get_settings


@dataclass(frozen=True)
class JoinVelocitySnapshot:
    """Join activity for a channel within the configured sliding window."""

    channel_id: int
    join_count: int
    window_seconds: float
    burst_threshold: int

    @property
    def is_burst(self) -> bool:
        """True when join volume meets or exceeds the burst threshold."""
        return self.join_count >= self.burst_threshold


class JoinVelocityTracker:
    """Thread-safe sliding-window join counter keyed by channel id."""

    def __init__(
        self,
        *,
        burst_threshold: int,
        window_seconds: float = 300.0,
    ) -> None:
        """Configure burst detection for join requests."""
        self._burst_threshold = burst_threshold
        self._window_seconds = window_seconds
        self._events: dict[int, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def record_join(self, channel_id: int) -> JoinVelocitySnapshot:
        """Record a join request and return the updated velocity snapshot."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._events[channel_id]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            bucket.append(now)
            count = len(bucket)
        return JoinVelocitySnapshot(
            channel_id=channel_id,
            join_count=count,
            window_seconds=self._window_seconds,
            burst_threshold=self._burst_threshold,
        )

    def reset(self) -> None:
        """Clear tracked join events (tests only)."""
        with self._lock:
            self._events.clear()


_tracker: JoinVelocityTracker | None = None


def _get_tracker() -> JoinVelocityTracker:
    """Return process-wide join velocity tracker."""
    global _tracker
    settings = get_settings()
    if (
        _tracker is None
        or _tracker._burst_threshold != settings.join_burst_threshold
        or _tracker._window_seconds != float(settings.join_burst_window_seconds)
    ):
        _tracker = JoinVelocityTracker(
            burst_threshold=settings.join_burst_threshold,
            window_seconds=float(settings.join_burst_window_seconds),
        )
    return _tracker


def record_join_request(channel_id: int) -> JoinVelocitySnapshot:
    """Record a channel join request and return the current velocity snapshot."""
    return _get_tracker().record_join(channel_id)


def reset_join_velocity_tracker() -> None:
    """Reset join velocity state (tests only)."""
    if _tracker is not None:
        _tracker.reset()
