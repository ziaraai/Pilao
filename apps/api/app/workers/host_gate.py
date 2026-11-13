"""One robot job at a time per buyer platform, and a pause between them (spec « Récupération
des DCE », § 5): a lock and the time of the last visit, in Redis, shared by every worker."""

import time
from typing import Protocol

from redis import Redis

from app.core.config import get_settings

LOCK_SECONDS = 600
GAP_SECONDS = 10.0


class HostGate(Protocol):
    def acquire(self, host: str) -> bool: ...

    def release(self, host: str) -> None: ...

    def wait_gap(self, host: str) -> None: ...


class RedisHostGate:
    def __init__(self, redis: Redis, ttl: int = LOCK_SECONDS, gap: float = GAP_SECONDS) -> None:
        self._redis, self._ttl, self._gap = redis, ttl, gap

    def acquire(self, host: str) -> bool:
        return bool(self._redis.set(f"dce-robot:{host}", "1", nx=True, ex=self._ttl))

    def release(self, host: str) -> None:
        self._redis.set(f"dce-robot:last:{host}", repr(time.time()), ex=int(self._gap) + 1)
        self._redis.delete(f"dce-robot:{host}")

    def wait_gap(self, host: str) -> None:
        last = self._redis.get(f"dce-robot:last:{host}")
        if last is None:
            return
        wait = self._gap - (time.time() - float(last))
        if wait > 0:
            time.sleep(wait)


def get_host_gate() -> HostGate:
    return RedisHostGate(Redis.from_url(get_settings().redis_url))
