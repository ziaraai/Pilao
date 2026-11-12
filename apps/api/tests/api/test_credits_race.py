"""Lot 4: two paid requests of the same company at the same instant (a double click served by
two API workers, a deposit while someone relaunches). Real commits on two connections: no
deadlock, and « one at a time » holds, so the credits are taken once (final review, I3)."""

import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    Bid,
    CreditEntry,
    DceAnalysis,
    DceVersion,
    Memoir,
    MemoirSection,
    Organization,
    User,
)
from app.services import credits
from app.services import dce_analysis as analysis_svc
from app.services import memoir_drafting as drafting
from app.services import profile_prefill as prefill

REAL_CREDITS = True


class NullQueue:
    """Every ``enqueue_*`` accepted, nothing run."""

    def __getattr__(self, name: str) -> Callable[..., None]:
        return lambda *args, **kwargs: None


@dataclass
class Company:
    org_id: uuid.UUID
    user_id: uuid.UUID


@pytest.fixture
def company(engine: Engine) -> Iterator[Company]:
    with Session(engine) as db:
        siret = f"9{uuid.uuid4().int % 10**13:013d}"
        org = Organization(siren=siret[:9], siret=siret, name="Course")
        db.add(org)
        db.flush()
        user = User(
            org_id=org.id, email=f"course-{uuid.uuid4().hex[:8]}@example.fr", role="org_admin"
        )
        db.add(user)
        db.add(CreditEntry(org_id=org.id, kind="grant", extra=50, reason="test"))
        db.commit()
        made = Company(org.id, user.id)
    yield made
    with engine.begin() as conn:  # every row of the company goes with it
        conn.execute(text("DELETE FROM organizations WHERE id = :id"), {"id": made.org_id})


@pytest.fixture(autouse=True)
def meet_at_the_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both requests wait for each other where the price is read (at most 2 s: a request held
    behind the other one's lock never comes)."""
    barrier = threading.Barrier(2)
    real = credits.price

    def price(db: Session, action: str) -> int:
        try:
            barrier.wait(timeout=2)
        except threading.BrokenBarrierError:
            pass
        return real(db, action)

    monkeypatch.setattr(credits, "price", price)


def race(engine: Engine, org_id: uuid.UUID, click: Callable[[Session, int], object]) -> list[str]:
    results: list[str] = []

    def run(i: int) -> None:
        with Session(engine, expire_on_commit=False) as db:
            scope_session(db, org_id)
            try:
                click(db, i)
                results.append("ok")
            except ApiError as exc:
                results.append(exc.code)
            except Exception as exc:  # noqa: BLE001 — a deadlock, reported as such
                results.append(type(exc).__name__)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return sorted(results)


def charges(engine: Engine, org_id: uuid.UUID) -> int:
    with Session(engine) as db:
        return int(
            db.scalar(
                select(func.count())
                .select_from(CreditEntry)
                .where(CreditEntry.org_id == org_id, CreditEntry.kind == "charge")
            )
        )


def _version(db: Session, org_id: uuid.UUID) -> DceVersion:
    bid = Bid(org_id=org_id, title="AO")
    db.add(bid)
    db.flush()
    version = DceVersion(
        org_id=org_id, bid_id=bid.id, version=1, status="ready", source_file_ids=[]
    )
    db.add(version)
    db.flush()
    return version


def _memoir(engine: Engine, org_id: uuid.UUID, status: str) -> tuple[uuid.UUID, uuid.UUID]:
    with Session(engine) as db:
        version = _version(db, org_id)
        analysis = DceAnalysis(
            org_id=org_id, bid_id=version.bid_id, dce_version_id=version.id, status="ready"
        )
        db.add(analysis)
        db.flush()
        memoir = Memoir(
            org_id=org_id,
            bid_id=version.bid_id,
            dce_analysis_id=analysis.id,
            version=1,
            status=status,
            outline_source="sector_default",
        )
        db.add(memoir)
        db.flush()
        section = MemoirSection(
            org_id=org_id,
            memoir_id=memoir.id,
            position=1,
            title="1. Moyens",
            status="ready" if status == "ready" else "pending",
        )
        db.add(section)
        db.commit()
        return memoir.id, section.id


def test_two_deposits_at_once_are_both_charged(engine: Engine, company: Company) -> None:
    with Session(engine) as db:
        versions = [_version(db, company.org_id).id for _ in range(2)]
        db.commit()

    def deposit(db: Session, i: int) -> None:
        version = db.get_one(DceVersion, versions[i])
        a = analysis_svc.request_analysis(db, version, NullQueue(), user_id=None, automatic=True)
        assert a.status == "pending"

    assert race(engine, company.org_id, deposit) == ["ok", "ok"]  # no deadlock
    assert charges(engine, company.org_id) == 2


def test_two_relaunches_at_once_are_charged_once(engine: Engine, company: Company) -> None:
    with Session(engine) as db:
        bid_id = _version(db, company.org_id).bid_id
        db.commit()

    def relaunch(db: Session, _: int) -> None:
        analysis_svc.rerun(db, db.get_one(Bid, bid_id), NullQueue(), company.user_id)

    assert race(engine, company.org_id, relaunch) == ["analysis_running", "ok"]
    assert charges(engine, company.org_id) == 1


def test_two_drafting_clicks_at_once_are_charged_once(engine: Engine, company: Company) -> None:
    memoir_id, _ = _memoir(engine, company.org_id, "draft")

    def write(db: Session, _: int) -> None:
        memoir = db.get_one(Memoir, memoir_id)  # loaded by the route, before the call
        drafting.start_generation(db, db.get_one(User, company.user_id), memoir, NullQueue())

    assert race(engine, company.org_id, write) == ["memoir_not_draft", "ok"]
    assert charges(engine, company.org_id) == 1


def test_two_regeneration_clicks_at_once_are_charged_once(engine: Engine, company: Company) -> None:
    _, section_id = _memoir(engine, company.org_id, "ready")

    def regenerate(db: Session, _: int) -> None:
        section = db.get_one(MemoirSection, section_id)  # loaded by the route
        user = db.get_one(User, company.user_id)
        drafting.regenerate_section(db, user, section, None, [], NullQueue())

    assert race(engine, company.org_id, regenerate) == ["ok", "section_busy"]
    assert charges(engine, company.org_id) == 1


def test_two_reading_clicks_at_once_are_charged_once(
    engine: Engine, company: Company, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prefill, "_ready_documents", lambda db: [object()])

    def read(db: Session, _: int) -> None:
        org = db.get_one(Organization, company.org_id)
        prefill.request_read(db, org, NullQueue(), company.user_id)

    assert race(engine, company.org_id, read) == ["already_running", "ok"]
    assert charges(engine, company.org_id) == 1
