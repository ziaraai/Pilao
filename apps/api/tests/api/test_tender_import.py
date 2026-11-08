"""Scheduled notice imports (P3-01, P3-02): real TED notices through the whole path."""

import copy
import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Tender, TenderImport, TenderMatch
from app.integrations.ted import TedUnavailable, to_tender
from app.schemas.tenders import TenderIn
from app.services.tender_import import _lock_key, next_since, run_import, watched_cpv_codes
from tests.api.test_tenders import company
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]
PARIS = ZoneInfo("Europe/Paris")
NOTICES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "ted_notices.json").read_text("utf-8")
)["notices"]
BY_NUMBER = {n["publication-number"]: n for n in NOTICES}
ORIGINAL, CHANGE_1, CHANGE_2 = "447747-2026", "497104-2026", "534002-2026"
ALES = "32bb2a4a-93d4-4ea5-ac34-bac809905d6c"  # procedure of the three notices above
SAINT_ETIENNE = "b67bfaba-c5de-4e8d-b05f-5560e23cf7cf"


class Reader:
    def __init__(self, *numbers: str, fail_after: int | None = None, **overrides: Any) -> None:
        self.notices = [copy.deepcopy(BY_NUMBER[n]) for n in numbers]
        for n in self.notices:
            n.update(overrides.get(n["publication-number"], {}))
        self.fail_after = fail_after
        self.calls: list[tuple[list[str], date]] = []

    def fetch(
        self,
        cpv_codes: list[str],
        since: date,
        limit: int | None = None,
        known: Callable[[list[str]], set[str]] | None = None,
    ) -> Iterator[TenderIn | None]:
        self.calls.append((cpv_codes, since))
        self.known = known
        for i, n in enumerate(self.notices):
            if self.fail_after is not None and i >= self.fail_after:
                raise TedUnavailable("HTTP 503")
            yield to_tender(n)
        yield None  # a notice the reader could not use


def tender(db: Session, source_id: str) -> Tender:
    found = db.scalar(select(Tender).where(Tender.source == "ted", Tender.source_id == source_id))
    assert found is not None, source_id
    return found


def test_a_procedure_its_changes_and_an_award(
    db: Session, outbox: Outbox, queue: FakeQueue
) -> None:
    # TED does not list them in publication order: the import sorts them
    reader = Reader(CHANGE_2, ORIGINAL, "756561-2026", CHANGE_1, "738785-2026")
    result = run_import(db, "ted", reader, outbox, queue, since=date(2026, 6, 1))
    assert (result.status, result.fetched, result.skipped) == ("done", 6, 1)
    assert (result.created, result.corrected) == (3, 2)

    ales = tender(db, ALES)
    assert ales.notice_type == "contract_notice"
    assert ales.deadline_at == datetime(2026, 8, 26, 11, 0, tzinfo=PARIS)  # last change wins
    assert [c["source_id"] for c in ales.corrections] == [CHANGE_1, CHANGE_2]
    # a change notice whose original is unknown stands for it
    st_etienne = tender(db, SAINT_ETIENNE)
    assert st_etienne.notice_type == "contract_notice" and st_etienne.departments == ["42"]
    assert tender(db, "756561-2026").notice_type == "award"

    run = db.scalar(select(TenderImport).where(TenderImport.source == "ted"))
    assert run is not None and (run.status, run.created, run.fetched) == ("done", 3, 6)
    assert run.finished_at is not None

    # the next pass reads the same notices again (overlap): nothing goes backwards
    again = run_import(db, "ted", Reader(ORIGINAL, CHANGE_1), outbox, queue)
    assert (again.created, again.updated, again.corrected) == (0, 0, 0)
    db.expire_all()
    ales = tender(db, ALES)
    assert ales.deadline_at == datetime(2026, 8, 26, 11, 0, tzinfo=PARIS)
    assert len(ales.corrections) == 2


def test_a_new_notice_reaches_the_companies_that_watch_it(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = company(make_client, outbox, queue, departments=["42"], max_amount_cents=None)
    future = {
        "738785-2026": {
            "deadline-receipt-tender-date-lot": ["2099-01-15+01:00"],
            "change-notice-version-identifier": None,  # here the notice itself
        }
    }
    result = run_import(db, "ted", Reader("738785-2026", **future), outbox, queue)
    assert result.matched == 1
    queue.drain_tenders()
    [match] = db.scalars(select(TenderMatch)).all()
    assert match.tender_id == tender(db, SAINT_ETIENNE).id
    notices = c.get("/tenders").json()
    assert [n["title"] for n in notices["items"]] == [
        "NETTOYAGE DES LOCAUX ADMINISTRATIFS D'HABITAT ET MÉTROPOLE"
    ]


def test_each_pass_starts_where_the_last_one_did(
    db: Session, outbox: Outbox, queue: FakeQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "tender_import_backfill_days", 14)
    today = datetime.now(UTC).date()
    assert next_since(db, "ted", today) == today - timedelta(days=14)  # first pass
    reader = Reader("756561-2026")
    run_import(db, "ted", reader, outbox, queue)
    assert reader.calls[0][1] == today - timedelta(days=14)
    assert next_since(db, "ted", today) == today - timedelta(days=1)  # one day of overlap
    assert next_since(db, "boamp", today) == today - timedelta(days=14)  # per source
    # the CPV codes searched: every trade, and every code a company watches
    assert "90911300" in reader.calls[0][0] and "90919200" in reader.calls[0][0]
    assert set(watched_cpv_codes(db)) >= {"90910000", "90610000"}


def test_a_failure_is_recorded_and_the_next_pass_starts_over(
    db: Session, outbox: Outbox, queue: FakeQueue
) -> None:
    today = datetime.now(UTC).date()
    ok = run_import(db, "ted", Reader("756561-2026"), outbox, queue, since=date(2026, 10, 1))
    assert ok.status == "done"
    failed = run_import(db, "ted", Reader(ORIGINAL, CHANGE_1, fail_after=1), outbox, queue)
    assert failed.status == "error" and failed.error == "TedUnavailable: HTTP 503"
    runs = db.scalars(select(TenderImport).order_by(TenderImport.created_at)).all()
    assert [r.status for r in runs] == ["done", "error"] and runs[1].error == failed.error
    assert next_since(db, "ted", today) == today - timedelta(days=1)  # from the last success


def test_two_passes_never_run_together(
    db: Session, outbox: Outbox, queue: FakeQueue, engine: Engine
) -> None:
    with engine.connect() as other:  # another scheduler holds the lock
        other.execute(text("select pg_advisory_lock(:k)"), {"k": _lock_key("ted")})
        busy = run_import(db, "ted", Reader(ORIGINAL), outbox, queue)
        other.execute(text("select pg_advisory_unlock(:k)"), {"k": _lock_key("ted")})
    assert busy.status == "busy"
    assert db.scalars(select(TenderImport)).all() == []  # nothing recorded, nothing read


def test_a_dry_run_reads_and_writes_nothing(db: Session, outbox: Outbox, queue: FakeQueue) -> None:
    result = run_import(db, "ted", Reader(ORIGINAL, "738785-2026"), outbox, queue, dry_run=True)
    assert (result.fetched, result.skipped, len(result.samples)) == (3, 1, 2)
    assert result.samples[0].title.startswith("Opération de travaux courants")
    assert db.scalars(select(Tender)).all() == [] and db.scalars(select(TenderImport)).all() == []


def test_the_reader_is_told_what_is_already_stored(
    db: Session, outbox: Outbox, queue: FakeQueue
) -> None:
    reader = Reader(ORIGINAL, CHANGE_1)
    run_import(db, "ted", reader, outbox, queue, since=date(2026, 6, 1))
    assert reader.known is not None
    # the notice itself, and a correction already applied to it: no need to read them again
    assert reader.known([ALES, CHANGE_1, CHANGE_2, "inconnu"]) == {ALES, CHANGE_1}


def test_reread_and_the_coverage_of_a_dry_run(
    db: Session, outbox: Outbox, queue: FakeQueue
) -> None:
    run_import(db, "ted", Reader(ORIGINAL), outbox, queue, since=date(2026, 6, 1))
    again = Reader(ORIGINAL)
    run_import(db, "ted", again, outbox, queue, since=date(2026, 6, 1), reread=True)
    assert again.known is None  # read again, stored or not
    dry = run_import(db, "ted", Reader(ORIGINAL, "738785-2026"), outbox, queue, dry_run=True)
    # [read, with a description, an amount, a documents link], per notice family
    assert dry.coverage == {"TED": [2, 2, 1, 2]}
