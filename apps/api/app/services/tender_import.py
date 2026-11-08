"""Scheduled notice imports (P3-01 BOAMP, P3-02 TED): fetch, convert, ingest, match.

Each pass searches from the start of the last pass that finished, one day earlier (the
upsert makes the overlap harmless), or ``tender_import_backfill_days`` back the first time.
A Postgres advisory lock keeps two passes of one source from running together (two
schedulers, a manual run during a scheduled one). Every pass leaves a ``tender_imports``
row: what was read and created, or the error.

Runs on an unscoped session: notices are global, then matched for every company.
"""

import logging
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Protocol, cast

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Mailer
from app.db.models import CompanyProfile, TenderImport
from app.domain.trades import TRADES
from app.schemas.tenders import TenderIn
from app.services.tenders import ingest, match_tenders
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.tender_import")
Source = Literal["boamp", "ted"]
BATCH = 200  # notices per ingest commit
OVERLAP = timedelta(days=1)


class Reader(Protocol):
    """A source: its notices published since a date, for these CPV codes, already
    converted (None for a notice it could not use)."""

    def fetch(
        self, cpv_codes: list[str], since: date, limit: int | None = None
    ) -> Iterable[TenderIn | None]: ...


@dataclass
class ImportResult:
    source: str
    since: date
    status: str = "done"  # done | error | busy (another pass is running)
    fetched: int = 0
    skipped: int = 0
    created: int = 0
    updated: int = 0
    corrected: int = 0
    matched: int = 0
    error: str | None = None
    samples: list[TenderIn] = field(default_factory=list)  # dry run only


def watched_cpv_codes(db: Session) -> list[str]:
    """Every CPV code a company watches, and those of every trade Pilao offers."""
    codes: dict[str, None] = {}
    for trade in TRADES.values():
        codes.update(dict.fromkeys(trade.cpv_codes))
    for profile_codes in db.scalars(select(CompanyProfile.cpv_codes)):
        codes.update(dict.fromkeys(profile_codes or []))
    return list(codes)


def next_since(db: Session, source: str, today: date) -> date:
    last = db.scalar(
        select(TenderImport)
        .where(TenderImport.source == source, TenderImport.status == "done")
        .order_by(TenderImport.created_at.desc())
        .limit(1)
    )
    if last is None:
        return today - timedelta(days=get_settings().tender_import_backfill_days)
    started = last.created_at.astimezone(UTC).date()
    return min(started - OVERLAP, today)


def _lock_key(source: str) -> int:
    return zlib.crc32(f"pilao:tender-import:{source}".encode())


def run_import(
    db: Session,
    source: Source,
    reader: Reader,
    mailer: Mailer,
    queue: JobQueue,
    since: date | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ImportResult:
    """One pass. ``dry_run``: read and convert only, nothing is written (server checks)."""
    today = now().date()
    start = since or next_since(db, source, today)
    result = ImportResult(source=source, since=start)
    cpv = watched_cpv_codes(db)
    if dry_run:
        for item in reader.fetch(cpv, start, limit):
            result.fetched += 1
            if item is None:
                result.skipped += 1
            elif len(result.samples) < 5:
                result.samples.append(item)
        return result

    key = _lock_key(source)
    if not db.execute(text("select pg_try_advisory_lock(:k)"), {"k": key}).scalar():
        result.status = "busy"
        logger.info("%s import already running: skipped", source)
        return result
    run = TenderImport(source=source, since=start, status="running")
    db.add(run)
    db.commit()
    try:
        batch: list[TenderIn] = []
        for item in reader.fetch(cpv, start, limit):
            result.fetched += 1
            if item is None:
                result.skipped += 1
                continue
            batch.append(item)
            if len(batch) >= BATCH:
                _ingest(db, batch, mailer, queue, result)
                batch = []
        _ingest(db, batch, mailer, queue, result)
    except Exception as exc:
        db.rollback()
        result.status, result.error = "error", f"{type(exc).__name__}: {exc}"[:2000]
        logger.exception("%s import failed", source)
    finally:
        _record(db, run, result, now())
        db.execute(text("select pg_advisory_unlock(:k)"), {"k": key})
        db.commit()
    logger.info("%s import: %s", source, _summary(result))
    return result


def _ingest(
    db: Session,
    batch: list[TenderIn],
    mailer: Mailer,
    queue: JobQueue,
    result: ImportResult,
) -> None:
    if not batch:
        return
    report = ingest(db, batch, mailer)  # commits
    result.created += report.created
    result.updated += report.updated
    result.corrected += report.corrected
    if report.to_match:
        result.matched += match_tenders(db, report.to_match, queue)


def _record(db: Session, run: TenderImport, result: ImportResult, at: datetime) -> None:
    fresh = db.get(TenderImport, run.id)
    if fresh is None:  # pragma: no cover - the row was committed before the pass
        return
    fresh.status = result.status
    fresh.finished_at = at
    for key in ("fetched", "skipped", "created", "updated", "corrected", "matched", "error"):
        setattr(fresh, key, getattr(result, key))


def _summary(r: ImportResult) -> str:
    return (
        f"depuis le {r.since:%d/%m/%Y} : {r.fetched} lue(s), {r.created} nouvelle(s), "
        f"{r.updated} mise(s) à jour, {r.corrected} rectifiée(s), {r.skipped} ignorée(s), "
        f"{r.matched} correspondance(s) avec les entreprises"
    )


def describe(r: ImportResult) -> str:
    """For the command line and the logs."""
    if r.status == "busy":
        return f"{r.source.upper()} : un import est déjà en cours, rien à faire."
    if r.status == "error":
        return f"{r.source.upper()} : échec ({r.error}) ; {_summary(r)}."
    return f"{r.source.upper()} {_summary(r)}."


def readers() -> dict[str, Callable[[], Reader]]:
    """The enabled sources, by name."""
    from app.integrations.ted import TedReader

    found: dict[str, Callable[[], Reader]] = {}
    s = get_settings()
    if s.ted_import_enabled:
        found["ted"] = TedReader
    if s.boamp_import_enabled:
        from app.integrations.boamp import BoampReader

        found["boamp"] = BoampReader
    return found


def run_all(db: Session, mailer: Mailer, queue: JobQueue) -> list[ImportResult]:
    """The scheduled job: every enabled source, one after the other; one failing source
    does not stop the others."""
    results = []
    for name, make in readers().items():
        results.append(run_import(db, cast(Source, name), make(), mailer, queue))
    return results
