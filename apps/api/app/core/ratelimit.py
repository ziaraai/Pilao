"""Tiny in-process sliding-window limiter for public endpoints.

Limit: per worker process. Behind several workers the effective limit is multiplied; move to
Redis (already in the stack) when public traffic justifies it.
"""

import time
from collections import defaultdict, deque

from app.core.errors import ApiError


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls, self.window = max_calls, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.max_calls:
            raise ApiError(429, "rate_limited", "Trop de requêtes. Réessayez dans un instant.")
        hits.append(now)
