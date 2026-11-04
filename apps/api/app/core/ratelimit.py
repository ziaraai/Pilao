"""Tiny in-process sliding-window limiter for public endpoints.

Limit: per worker process. Behind several workers the effective limit is multiplied; move to
Redis (already in the stack) when public traffic justifies it.
"""

import threading
import time
from collections import deque

from app.core.errors import ApiError

_SWEEP_EVERY = 1000  # keys: drop idle ones so memory does not grow with every client seen


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls, self.window = max_calls, window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:  # sync endpoints run in a thread pool: check-then-append must be atomic
            if len(self._hits) >= _SWEEP_EVERY:
                cutoff = now - self.window
                self._hits = {k: h for k, h in self._hits.items() if h and h[-1] > cutoff}
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.max_calls:
                raise ApiError(429, "rate_limited", "Trop de requêtes. Réessayez dans un instant.")
            hits.append(now)
