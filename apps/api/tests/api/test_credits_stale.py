"""Lot 4: a work left for dead (worker killed, timeout, every retry spent) gives its credits
back, never stays « en cours », and is never run afterwards (final review, C2)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import DceAnalysis, Job, MemoirSection
from app.services.stale_works import sweep_stale_works
from tests.api.helpers import signed_in_client
from tests.api.test_credits_actions import _read_ready, deposited, entries, top_up, total, writer
from tests.api.test_memoir_drafting import WriterModel, latest, prepared, section
from tests.conftest import FakeQueue, Outbox

REAL_CREDITS = True
Factory = Callable[[], TestClient]
__all__ = ["writer"]  # the fixture, imported for its name
LONG_AGO = datetime.now(UTC) - timedelta(hours=3)


def _age_analyses(db: Session) -> None:
    db.execute(update(DceAnalysis).values(updated_at=LONG_AGO))
    db.commit()


def test_a_dead_analysis_is_closed_refunded_and_never_run(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)  # charged 2: 5 left, the worker never ran it
    assert total(c) == 5
    _age_analyses(db)

    assert sweep_stale_works(db, queue) == 1
    a = c.get(f"/bids/{bid}/analysis").json()
    assert (a["status"], a["error"]) == ("error", "L'analyse s'est interrompue. Relancez-la.")
    [back] = entries(db, "refund", "dce_analysis")
    assert back.reason == "Remboursé : l'analyse n'a pas abouti." and total(c) == 7
    job = db.scalar(select(Job).where(Job.kind == "analyze_dce"))
    assert job is not None and job.status == "error"

    queue.drain_analyses()  # the forgotten RQ job finally runs: it does nothing
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "error"
    assert sweep_stale_works(db, queue) == 0  # closed once


def test_a_live_analysis_is_left_alone(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)
    assert sweep_stale_works(db, queue) == 0
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "pending"
    assert entries(db, "refund") == [] and total(c) == 5


def test_a_relaunch_closes_the_dead_analysis_first(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)
    _age_analyses(db)
    assert c.post(f"/bids/{bid}/analysis").status_code == 202
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "ready"
    assert len(entries(db, "charge", "dce_analysis")) == 2
    assert len(entries(db, "refund", "dce_analysis")) == 1 and total(c) == 5  # paid once


def test_a_dead_chapter_is_closed_refunded_and_the_memoir_finishes(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    top_up(db, 10)
    m = prepared(c, queue)
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    queue.drain_memoir()
    ready = section(latest(c, m["id"]), "2. Méthodologie")
    assert c.post(f"/memoir-sections/{ready['id']}/regenerate", json={}).status_code == 202
    before = total(c)
    queue.pending_sections.clear()  # the worker died with the job
    db.execute(update(MemoirSection).values(updated_at=LONG_AGO))
    db.commit()

    assert sweep_stale_works(db, queue) == 1
    m = latest(c, m["id"])
    dead = section(m, "2. Méthodologie")
    assert dead["status"] == "error"
    assert dead["error"] == "La rédaction de ce chapitre s'est interrompue. Relancez-la."
    assert m["status"] == "ready"  # nothing else is being drafted
    [back] = entries(db, "refund", "chapter_regeneration")
    assert back.reason == "Remboursé : la régénération n'a pas abouti." and total(c) == before + 1


def test_a_dead_reading_is_closed_and_refunded(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    _read_ready(c, queue, monkeypatch)
    assert c.post("/profile/suggestions/read").status_code == 202
    assert total(c) == 6
    db.execute(update(Job).where(Job.kind == "profile_prefill").values(created_at=LONG_AGO))
    db.commit()

    assert sweep_stale_works(db, queue) == 1
    [back] = entries(db, "refund", "profile_prefill")
    assert back.reason == "Remboursé : la lecture n'a pas abouti." and total(c) == 7
    queue.drain_profile_prefill()  # the forgotten job: nothing read, nothing charged again
    job = db.scalar(select(Job).where(Job.kind == "profile_prefill"))
    assert job is not None and job.status == "error"


def test_a_new_reading_closes_the_dead_one_first(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    _read_ready(c, queue, monkeypatch)
    assert c.post("/profile/suggestions/read").status_code == 202
    queue.pending_prefill.clear()
    db.execute(update(Job).where(Job.kind == "profile_prefill").values(created_at=LONG_AGO))
    db.commit()
    assert c.post("/profile/suggestions/read").status_code == 202
    queue.drain_profile_prefill()
    assert len(entries(db, "charge", "profile_prefill")) == 2
    assert len(entries(db, "refund", "profile_prefill")) == 1 and total(c) == 6  # paid once
