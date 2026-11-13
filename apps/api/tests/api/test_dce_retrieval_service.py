"""DCE retrieval on request (spec « Récupération des DCE », § 4.1, § 4.2, § 5): the service, the
job and the update hook, with a fake robot (no browser, no network)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import runtime
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    Bid,
    CreditEntry,
    DceAnalysis,
    DceFetch,
    DceFile,
    DceVersion,
    File,
    Job,
    Organization,
    PlatformSetting,
    Tender,
    User,
)
from app.integrations.atexo import RobotError, RobotUnavailable
from app.services import dce_retrieval as svc
from app.services.stale_works import sweep_stale_works
from tests.api.helpers import signed_in_client
from tests.api.test_bids import RC, deposit, new_bid, zipped
from tests.conftest import FakeQueue, FakeRobot, Outbox

PLACE = "https://www.marches-publics.gouv.fr/entreprise/consultation/3091292?orgAcronyme=h8j"
CONTACT = svc.Contact("Sabrina", "Martin", "sabrina@exemple.fr")


class World:
    def __init__(self, make_client: Any, outbox: Outbox, db: Session, n: int = 1) -> None:
        self.client = signed_in_client(make_client, outbox, n)
        self.bid_id = uuid.UUID(new_bid(self.client))
        self.db = db
        tender = Tender(source="ted", source_id=f"t-{n}", title="Nettoyage", documents_url=PLACE)
        db.add(tender)
        db.flush()
        self.bid.tender_id = tender.id
        db.commit()

    @property
    def bid(self) -> Bid:
        return self.db.get_one(Bid, self.bid_id, populate_existing=True)

    @property
    def org(self) -> Organization:
        return self.db.get_one(Organization, self.bid.org_id, populate_existing=True)

    @property
    def user(self) -> User:
        return self.db.scalars(select(User).where(User.org_id == self.org.id)).one()

    def request(self, queue: FakeQueue, **kw: Any) -> DceFetch:
        args: dict[str, Any] = {"mode": None, "remember": False, "contact": None, **kw}
        return svc.request_retrieval(self.db, self.org, self.user, self.bid, queue=queue, **args)


@pytest.fixture
def world(make_client: Any, outbox: Outbox, db: Session) -> World:
    return World(make_client, outbox, db)


def _code(call: Any) -> str:
    with pytest.raises(ApiError) as caught:
        call()
    return caught.value.code


def _fetch(db: Session, fetch_id: uuid.UUID) -> DceFetch:
    return db.get_one(DceFetch, fetch_id, populate_existing=True)


def test_choice_needed_the_first_time(world: World, queue: FakeQueue) -> None:
    assert _code(lambda: world.request(queue)) == "retrieval_choice_needed"


def test_remembered_mode_and_contact(world: World, queue: FakeQueue, db: Session) -> None:
    fetch = world.request(queue, mode="identified", remember=True, contact=CONTACT)
    org = world.org
    assert org.dce_retrieval_mode == "identified"
    assert (org.buyer_contact_first_name, org.buyer_contact_last_name) == ("Sabrina", "Martin")
    assert org.buyer_contact_email == "sabrina@exemple.fr"
    assert fetch.status == "pending" and fetch.kind == "retrieval" and fetch.site == "PLACE"
    assert db.scalars(select(Job).where(Job.ref_id == fetch.id, Job.kind == "fetch_dce")).one()
    assert queue.pending_fetches == [(fetch.id, 0)]
    queue.drain_fetches(FakeRobot())
    queue.drain_dce()  # the first version is read: a new retrieval may start
    again = world.request(queue)  # no mode: the company's
    assert again.mode == "identified"


def test_identified_without_contact(world: World, queue: FakeQueue) -> None:
    assert _code(lambda: world.request(queue, mode="identified")) == "contact_incomplete"


def test_fetch_deposits_like_a_deposit(world: World, queue: FakeQueue, db: Session) -> None:
    fetch = world.request(queue, mode="anonymous", remember=True)
    queue.drain_fetches(FakeRobot())
    version = db.scalars(select(DceVersion).where(DceVersion.bid_id == world.bid_id)).one()
    assert (version.origin, version.source_url) == ("retrieval", PLACE)
    assert version.uploaded_by == world.user.id
    done = _fetch(db, fetch.id)
    assert (done.status, done.outcome, done.dce_version_id) == ("done", "ok", version.id)
    assert done.size_label == "0,01 Mo"
    watch = world.bid.dce_watch
    assert watch is not None
    assert watch["size_label"] == "0,01 Mo" and watch["failures"] == 0
    assert watch["deadline_at"] == "2026-11-30T11:00:00+00:00"
    queue.drain_dce()
    kinds = set(
        db.scalars(select(DceFile.detected_kind).where(DceFile.dce_version_id == version.id))
    )
    assert kinds == {"rc", "cctp"}
    assert db.scalars(select(DceAnalysis).where(DceAnalysis.dce_version_id == version.id)).one()
    charge = db.scalars(
        select(CreditEntry).where(
            CreditEntry.kind == "charge", CreditEntry.action == "dce_analysis"
        )
    ).one()
    assert charge.bid_id == world.bid_id


def test_identity_sent_only_in_identified_mode(world: World, queue: FakeQueue) -> None:
    robot = FakeRobot()
    world.request(queue, mode="identified", remember=False, contact=CONTACT)
    queue.drain_fetches(robot)
    queue.drain_dce()
    identity = robot.calls[-1][1]
    assert identity.company_name == world.org.name
    assert (identity.siren, identity.siret) == (world.org.siren, world.org.siret)
    assert (identity.first_name, identity.email) == ("Sabrina", "sabrina@exemple.fr")
    world.request(queue, mode="anonymous")
    queue.drain_fetches(robot)
    assert robot.calls[-1][1] is None


@pytest.mark.parametrize("outcome", ["closed", "captcha", "too_big", "robots", "refused_identity"])
def test_robot_errors_become_messages(
    world: World, queue: FakeQueue, db: Session, outcome: str
) -> None:
    fetch = world.request(queue, mode="anonymous")
    queue.drain_fetches(FakeRobot(RobotError(outcome, f"message {outcome}")))
    failed = _fetch(db, fetch.id)
    assert (failed.status, failed.outcome, failed.message) == (
        "error",
        outcome,
        f"message {outcome}",
    )
    assert db.scalars(select(DceVersion).where(DceVersion.bid_id == world.bid_id)).all() == []
    job = db.scalars(select(Job).where(Job.ref_id == fetch.id)).one()
    assert job.status == "done"  # an expected refusal is not a failure of Pilao


def test_unavailable_is_retried_then_reported(
    world: World, queue: FakeQueue, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetch = world.request(queue, mode="anonymous")
    robot = FakeRobot(RobotUnavailable("down"))
    monkeypatch.setattr(svc, "will_retry", lambda: True)
    with pytest.raises(RobotUnavailable):
        queue.drain_fetches(robot)
    assert _fetch(db, fetch.id).status == "pending"
    monkeypatch.setattr(svc, "will_retry", lambda: False)
    queue.run_fetch(fetch.id, robot)
    failed = _fetch(db, fetch.id)
    assert (failed.status, failed.outcome) == ("error", "unavailable")
    assert failed.message == "La plateforme ne répond pas. Réessayez plus tard."
    assert db.scalars(select(Job).where(Job.ref_id == fetch.id)).one().status == "error"


def test_second_click_refused(world: World, queue: FakeQueue) -> None:
    world.request(queue, mode="anonymous")
    assert _code(lambda: world.request(queue, mode="anonymous")) == "retrieval_running"


def test_deposit_in_progress(world: World, queue: FakeQueue) -> None:
    assert deposit(world.client, str(world.bid_id), ("RC.pdf", RC)).status_code == 202
    assert _code(lambda: world.request(queue, mode="anonymous")) == "dce_processing"


def test_robot_disabled(world: World, queue: FakeQueue, db: Session) -> None:
    db.add(PlatformSetting(key="dce_robot.enabled", value=False))
    db.commit()
    runtime.invalidate()
    assert _code(lambda: world.request(queue, mode="anonymous")) == "robot_disabled"


def test_home_link_is_not_automatic(world: World, queue: FakeQueue, db: Session) -> None:
    tender = db.get_one(Tender, world.bid.tender_id)
    tender.documents_url = "https://www.marches-publics.gouv.fr/?page=Entreprise.AccueilEntreprise"
    db.commit()
    assert _code(lambda: world.request(queue, mode="anonymous")) == "not_automatic"


def test_private_link_refused(world: World, queue: FakeQueue, db: Session) -> None:
    svc.set_link(
        db, world.user, world.bid, "https://10.0.0.5/entreprise/consultation/1?orgAcronyme=a"
    )
    assert _code(lambda: world.request(queue, mode="anonymous")) == "not_automatic"


def test_bad_link(world: World, db: Session) -> None:
    assert _code(lambda: svc.set_link(db, world.user, world.bid, "pas un lien")) == "bad_link"
    svc.set_link(db, world.user, world.bid, f"  {PLACE}#pub ")
    assert world.bid.dce_url == PLACE
    source = svc.source_for(db, world.bid)
    assert source is not None and source.automatic


def test_bid_deleted_meanwhile(world: World, queue: FakeQueue, db: Session) -> None:
    files_before = db.scalar(select(func.count()).select_from(File))
    world.request(queue, mode="anonymous")
    robot = FakeRobot(on_fetch=lambda: world.client.delete(f"/bids/{world.bid_id}"))
    queue.drain_fetches(robot)  # no exception
    assert db.scalar(select(func.count()).select_from(File)) == files_before
    assert robot.written and not robot.written[0].exists()  # the temporary file is gone


def test_not_a_zip(world: World, queue: FakeQueue, db: Session) -> None:
    fetch = world.request(queue, mode="anonymous")
    queue.drain_fetches(FakeRobot(b"<html><body>Erreur 500</body></html>"))
    failed = _fetch(db, fetch.id)
    assert (failed.status, failed.outcome) == ("error", "unreadable")
    assert failed.message
    assert db.scalars(select(DceVersion).where(DceVersion.bid_id == world.bid_id)).all() == []


def test_busy_site_is_postponed(world: World, queue: FakeQueue, db: Session) -> None:
    fetch = world.request(queue, mode="anonymous")
    queue.gate.free = False
    queue.drain_fetches(FakeRobot())
    assert _fetch(db, fetch.id).status == "pending"
    assert queue.pending_fetches == [(fetch.id, 60)]


def test_update_version_mails_and_waits_for_a_click(
    world: World, queue: FakeQueue, db: Session, outbox: Outbox
) -> None:
    world.request(queue, mode="anonymous")
    queue.drain_fetches(FakeRobot())
    queue.drain_dce()
    analyses = db.scalar(select(func.count()).select_from(DceAnalysis))
    charges = db.scalar(
        select(func.count()).select_from(CreditEntry).where(CreditEntry.kind == "charge")
    )
    update = DceFetch(
        org_id=world.org.id,
        bid_id=world.bid_id,
        kind="update",
        mode="anonymous",
        site="PLACE",
        requested_by=world.user.id,
    )
    db.add(update)
    db.flush()
    db.add(Job(kind="fetch_dce", ref_id=update.id, org_id=world.org.id, status="pending"))
    db.commit()
    outbox.sent.clear()
    queue.run_fetch(update.id, FakeRobot(zipped({"RC.pdf": RC, "AE.pdf": RC})))
    queue.drain_dce()
    latest = db.scalars(
        select(DceVersion)
        .where(DceVersion.bid_id == world.bid_id)
        .order_by(DceVersion.version.desc())
    ).first()
    assert latest is not None and (latest.origin, latest.version) == ("update", 2)
    assert latest.uploaded_by == world.user.id
    assert db.scalar(select(func.count()).select_from(DceAnalysis)) == analyses
    assert (
        db.scalar(select(func.count()).select_from(CreditEntry).where(CreditEntry.kind == "charge"))
        == charges
    )
    [mail] = outbox.sent
    assert mail.to == world.user.email
    assert mail.subject == "Le DCE de « Nettoyage des écoles » a changé"
    assert latest.diff_summary and latest.diff_summary in mail.body
    assert f"/dossiers/{world.bid_id}" in mail.body


def test_stale_fetch_is_closed(world: World, queue: FakeQueue, db: Session) -> None:
    fetch = world.request(queue, mode="anonymous")
    row = _fetch(db, fetch.id)
    row.status, row.created_at = "running", datetime.now(UTC) - timedelta(seconds=1300)
    db.commit()
    sweep_stale_works(db, queue)
    closed = _fetch(db, fetch.id)
    assert (closed.status, closed.message) == (
        "error",
        "La récupération a été interrompue. Réessayez.",
    )


def test_other_company_cannot_see_or_run(
    world: World, queue: FakeQueue, make_client: Any, outbox: Outbox, conn: Any
) -> None:
    from tests.conftest import _new_session

    world.request(queue, mode="anonymous")
    other = World(make_client, outbox, world.db, n=2)
    with _new_session(conn) as session:
        scope_session(session, other.org.id)
        assert svc.latest_fetch(session, world.bid_id) is None
        assert svc.latest_fetch(session, other.bid_id) is None
    with _new_session(conn) as session:
        scope_session(session, world.org.id)
        assert svc.latest_fetch(session, world.bid_id) is not None
