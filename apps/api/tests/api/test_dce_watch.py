"""The daily watch of the DCE retrieved by the robot (spec « Récupération des DCE », § 4.3)."""

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from rq import cron
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import runtime
from app.db.models import DceFetch, DceVersion, Organization, PlatformSetting
from app.domain.dce_sources import PageFacts
from app.integrations.atexo import RobotError, RobotUnavailable
from app.services import dce_retrieval as svc
from tests.api.test_bids import RC, processed, zipped
from tests.api.test_dce_retrieval_service import CONTACT, World
from tests.conftest import FakeQueue, FakeRobot, Outbox

NOW = datetime(2026, 11, 14, 5, 40, tzinfo=UTC)
DEADLINE = datetime(2026, 11, 30, 11, 0, tzinfo=UTC)


def retrieved(world: World, queue: FakeQueue, mode: str = "anonymous", **kw: Any) -> None:
    world.request(queue, mode=mode, **kw)
    queue.drain_fetches(FakeRobot())
    queue.drain_dce()


def watch(db: Session, robot: FakeRobot, queue: FakeQueue, outbox: Outbox) -> svc.WatchReport:
    return svc.watch_dces(db, robot, queue, outbox, queue.gate, NOW)


def checks(db: Session, world: World) -> list[DceFetch]:
    return list(
        db.scalars(
            select(DceFetch)
            .where(DceFetch.bid_id == world.bid_id, DceFetch.kind == "check")
            .order_by(DceFetch.created_at)
        )
    )


@pytest.fixture
def world(make_client: Any, outbox: Outbox, db: Session) -> World:
    return World(make_client, outbox, db)


def test_unchanged(world: World, queue: FakeQueue, db: Session, outbox: Outbox) -> None:
    retrieved(world, queue)
    report = watch(db, FakeRobot(), queue, outbox)
    assert (report.checked, report.changed, report.failed) == (1, 0, 0)
    [check] = checks(db, world)
    assert (check.status, check.outcome) == ("done", "unchanged")
    assert world.bid.dce_watch is not None
    assert world.bid.dce_watch["checked_at"] == NOW.isoformat()
    assert queue.pending_fetches == []


def test_size_changed_fetches_an_update(
    world: World, queue: FakeQueue, db: Session, outbox: Outbox
) -> None:
    retrieved(world, queue)
    outbox.sent.clear()
    report = watch(db, FakeRobot(facts=PageFacts("0,02 Mo", DEADLINE, False)), queue, outbox)
    assert report.changed == 1
    [(update_id, _)] = queue.pending_fetches
    update = db.get_one(DceFetch, update_id)
    assert (update.kind, update.mode) == ("update", "anonymous")
    queue.drain_fetches(FakeRobot(zipped({"RC.pdf": RC, "AE.pdf": RC})))
    queue.drain_dce()
    latest = db.scalars(
        select(DceVersion)
        .where(DceVersion.bid_id == world.bid_id)
        .order_by(DceVersion.version.desc())
    ).first()
    assert latest is not None and latest.origin == "update"
    assert latest.uploaded_by == world.user.id  # the requester of the first retrieval
    assert [m.subject for m in outbox.sent] == ["Le DCE de « Nettoyage des écoles » a changé"]
    from app.db.models import DceAnalysis

    assert (
        db.scalars(select(DceAnalysis).where(DceAnalysis.dce_version_id == latest.id)).all() == []
    )


def test_identified_update_without_contact_goes_anonymous(
    world: World, queue: FakeQueue, db: Session, outbox: Outbox
) -> None:
    retrieved(world, queue, mode="identified", contact=CONTACT)
    svc.save_settings(db, world.user, world.org, "identified", svc.Contact(None, None, None))
    watch(db, FakeRobot(facts=PageFacts("0,02 Mo", DEADLINE, False)), queue, outbox)
    [(update_id, _)] = queue.pending_fetches
    assert db.get_one(DceFetch, update_id).mode == "anonymous"


def test_deadline_changed(world: World, queue: FakeQueue, db: Session, outbox: Outbox) -> None:
    retrieved(world, queue)
    outbox.sent.clear()
    later = datetime(2026, 12, 5, 11, 0, tzinfo=UTC)
    report = watch(db, FakeRobot(facts=PageFacts("0,01 Mo", later, False)), queue, outbox)
    assert report.changed == 1
    assert world.bid.deadline_at == later
    assert queue.pending_fetches == []  # same files: nothing to fetch
    [mail] = outbox.sent
    assert mail.subject == "La date limite de « Nettoyage des écoles » a changé"
    assert "30/11 12:00 → 05/12 12:00" in mail.body
    assert world.bid.dce_watch is not None
    assert world.bid.dce_watch["deadline_at"] == later.isoformat()


def test_missing_facts_are_not_changes(
    world: World, queue: FakeQueue, db: Session, outbox: Outbox
) -> None:
    retrieved(world, queue)
    report = watch(db, FakeRobot(facts=PageFacts(None, None, False)), queue, outbox)
    assert report.changed == 0
    assert queue.pending_fetches == []
    assert checks(db, world)[0].outcome == "unchanged"
    state = world.bid.dce_watch
    assert state is not None
    assert state["size_label"] == "0,01 Mo"  # the last known values are kept
    assert state["deadline_at"] == DEADLINE.isoformat()


def test_three_failures_stop_the_watch(
    world: World, queue: FakeQueue, db: Session, outbox: Outbox
) -> None:
    retrieved(world, queue)
    down = FakeRobot(facts=RobotUnavailable("down"))
    for _ in range(3):
        assert watch(db, down, queue, outbox).failed == 1
    state = world.bid.dce_watch
    assert state is not None and state["failures"] == 3 and state["stopped"] is True
    assert watch(db, FakeRobot(), queue, outbox).checked == 0
    world.request(queue, mode="anonymous")  # a successful retrieval starts it again
    queue.drain_fetches(FakeRobot())
    state = world.bid.dce_watch
    assert state is not None and state["failures"] == 0 and state["stopped"] is False
    queue.drain_dce()
    assert watch(db, FakeRobot(), queue, outbox).checked == 1


def test_a_closed_consultation_counts_as_a_failure(
    world: World, queue: FakeQueue, db: Session, outbox: Outbox
) -> None:
    retrieved(world, queue)
    assert watch(db, FakeRobot(facts=RobotError("closed")), queue, outbox).failed == 1
    assert checks(db, world)[0].outcome == "closed"


def test_who_is_watched(make_client: Any, queue: FakeQueue, db: Session, outbox: Outbox) -> None:
    worlds = [World(make_client, outbox, db, n) for n in range(1, 7)]
    for w in worlds[:5]:
        retrieved(w, queue)
    submitted, past, _, suspended, no_module, by_hand = worlds
    submitted.client.patch(f"/bids/{submitted.bid_id}", json={"status": "submitted"})
    past.bid.deadline_at = NOW - timedelta(hours=1)
    suspended.org.suspended_at = NOW
    no_module.org.modules = ["veille"]
    db.commit()
    processed(by_hand.client, queue, str(by_hand.bid_id), ("RC.pdf", RC))  # deposited by hand
    robot = FakeRobot()
    report = watch(db, robot, queue, outbox)
    assert report.checked == 1  # only worlds[2]
    assert checks(db, worlds[2]) and not checks(db, submitted) and not checks(db, by_hand)
    db.add(PlatformSetting(key="dce_robot.enabled", value=False))
    db.commit()
    runtime.invalidate()
    assert watch(db, robot, queue, outbox).checked == 0


def test_cron_schedule() -> None:
    module = importlib.import_module("app.workers.cron")
    cron._job_data_registry.clear()
    importlib.reload(module)
    jobs = {job["func"].__name__: job for job in cron._job_data_registry}
    assert jobs["watch_dces_job"]["cron"] == "40 5 * * *"
    assert jobs["watch_dces_job"]["job_timeout"] == 3600


def _org(db: Session, world: World) -> Organization:
    return db.get_one(Organization, world.org.id)
