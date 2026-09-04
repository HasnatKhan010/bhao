"""Politeness primitives: a token bucket, not scattered sleeps (05-TRACK-A-INGEST.md)."""

from __future__ import annotations

import threading
import time


class TokenBucket:
    """Allows one request every `interval` seconds, enforced centrally."""

    def __init__(self, interval: float = 2.0) -> None:
        self.interval = max(interval, 0.0)
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a token is available. Returns seconds waited."""
        waited = 0.0
        with self._lock:
            now = time.monotonic()
            earliest = self._last + self.interval
            if earliest > now:
                waited = earliest - now
                if waited > 0:
                    time.sleep(waited)
                now = time.monotonic()
            self._last = now
            return waited
