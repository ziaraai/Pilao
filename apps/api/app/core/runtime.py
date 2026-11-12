"""The settings in use (lot 5, ADR-044): the administration's value, else the server's.

Every process (API, workers, scheduler) keeps a snapshot of the ``platform_settings`` rows,
read again at most every ``REFRESH_SECONDS``; the process that writes calls ``invalidate()``.
A change thus reaches every process in under a minute. The server's values are read from
``get_settings()`` at each call, never cached here.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select

from app.core import crypto
from app.core.config import get_settings
from app.db.models import PlatformSetting
from app.platform_settings import BY_NAME

logger = logging.getLogger("pilao.runtime")

REFRESH_SECONDS = 30
KEY = "openrouter_api_key"


@dataclass(frozen=True)
class Snapshot:
    values: dict[str, Any] = field(default_factory=dict)
    key: str | None = None
    key_last4: str | None = None
    key_unreadable: bool = False
    updated: dict[str, tuple[datetime, uuid.UUID | None]] = field(default_factory=dict)


Loader = Callable[[], list[PlatformSetting]]

_lock = threading.Lock()
_snapshot: Snapshot | None = None
_taken_at = 0.0
_loader: Loader | None = None
_overrides: dict[str, Any] = {}  # this process only: the phase 0 evaluation (eval-models)


def _read_rows() -> list[PlatformSetting]:
    if _loader is not None:
        return _loader()
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:  # unscoped: settings belong to the platform
        return list(db.scalars(select(PlatformSetting)))


def _load() -> Snapshot:
    values: dict[str, Any] = {}
    updated: dict[str, tuple[datetime, uuid.UUID | None]] = {}
    key = last4 = None
    unreadable = False
    for row in _read_rows():
        updated[row.key] = (row.updated_at, row.updated_by)
        if row.key == KEY:
            last4 = row.secret_last4
            try:
                key = crypto.decrypt(row.secret or "", KEY)
            except crypto.DecryptError:
                unreadable = True
                logger.warning("the OpenRouter key set in the administration is unreadable")
        else:
            values[row.key] = row.value
    return Snapshot(values, key, last4, unreadable, updated)


def snapshot() -> Snapshot:
    global _snapshot, _taken_at
    with _lock:
        now = time.monotonic()
        if _snapshot is None or now - _taken_at > REFRESH_SECONDS:
            _snapshot, _taken_at = _load(), now
        return _snapshot


def invalidate() -> None:
    global _snapshot
    with _lock:
        _snapshot = None


def set_loader(load: Loader | None) -> None:
    """Tests: read the rows through the test's own connection (``None``: the database)."""
    global _loader
    _loader = load
    invalidate()


def source(name: str) -> Literal["admin", "server"]:
    if name == KEY:
        return "admin" if KEY in snapshot().updated else "server"
    return "admin" if name in snapshot().values else "server"


def effective(name: str) -> Any:
    """The administration's value when there is one (an empty address included: « aucune »),
    else the server's."""
    if name in _overrides:
        return _overrides[name]
    if name == KEY:
        return api_key()
    current = snapshot().values
    if name in current:
        return current[name]
    return BY_NAME[name].server(get_settings())


def api_key() -> str | None:
    """The key set here and readable, else the server's, else None (LiteLLM then reads the
    environment, as before)."""
    return snapshot().key or get_settings().openrouter_api_key or None


def model_for_task(task: str) -> str:
    return str(effective(f"model.{task}") or "")


@contextmanager
def overridden(values: dict[str, Any]) -> Iterator[None]:
    """Values forced in this process, over the administration's and the server's: the phase 0
    evaluation tries its own model whatever is set in the administration."""
    saved = dict(_overrides)
    _overrides.update(values)
    try:
        yield
    finally:
        _overrides.clear()
        _overrides.update(saved)
