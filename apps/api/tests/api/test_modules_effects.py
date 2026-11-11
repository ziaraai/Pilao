"""What follows a company's modules (lot 3, spec §3.2, §3.3, §5.3)."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bid, TenderMatch
from app.services.alerts import run_daily
from tests.api.test_alerts import mails_to, paris
from tests.api.test_modules import set_modules
from tests.api.test_tenders import (  # noqa: F401 - the scorer fixture
    Factory,
    ScoreModel,
    company,
    load,
    notice,
    scorer,
    tender_id,
)
from tests.api.test_vault import TODAY, confirm, deposit
from tests.conftest import FakeQueue, Outbox


def test_dashboard_without_veille(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue)
    scorer.scores = {"Nettoyage A": 90}
    load(db, queue, outbox, notice("A"))
    assert c.get("/dashboard").json()["new_tenders"] == 1
    set_modules(db, "user1@example.fr", ["reponse"])

    d = c.get("/dashboard").json()
    assert (d["new_tenders"], d["best_tenders"], d["tenders_connected"]) == (0, [], False)


def test_dashboard_without_reponse(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    assert c.post("/bids", json={"title": "Gymnase"}).status_code == 201
    set_modules(db, "user1@example.fr", ["veille"])

    d = c.get("/dashboard").json()
    assert d["bids"] == [] and d["actions"] == []
    assert d["results"]["deposited"] == 0 and d["time_saved"]["bids"] == 0
    assert [s["key"] for s in d["getting_started"]] == ["profile"]


def test_dashboard_without_any_module(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    set_modules(db, "user1@example.fr", [])
    res = c.get("/dashboard")
    assert res.status_code == 200
    assert [s["key"] for s in res.json()["getting_started"]] == ["profile"]


def test_track_without_reponse(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"))
    set_modules(db, "user1@example.fr", ["veille"])

    res = c.post(f"/tenders/{tender_id(db, 'A')}/track")
    assert res.status_code == 201 and res.json() == {"bid": None}
    match = db.scalar(select(TenderMatch))
    assert match is not None and match.status == "tracked" and match.bid_id is None
    assert db.scalar(select(Bid)) is None


def test_track_with_reponse_unchanged(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"))
    bid = c.post(f"/tenders/{tender_id(db, 'A')}/track").json()["bid"]
    assert bid is not None and bid["title"] == "Nettoyage A"


def test_tracked_bid_kept_when_reponse_disabled(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"))
    bid_id = c.post(f"/tenders/{tender_id(db, 'A')}/track").json()["bid"]["id"]
    set_modules(db, "user1@example.fr", ["veille"])

    tender = c.get(f"/tenders/{tender_id(db, 'A')}").json()
    assert tender["status"] == "tracked" and tender["bid_id"] == bid_id
    assert db.get(Bid, bid_id) is not None


def test_background_skips_without_veille(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue, min_score_alert=10)
    load(db, queue, outbox, notice("A"))
    assert c.post(f"/tenders/{tender_id(db, 'A')}/track").status_code == 201
    set_modules(db, "user1@example.fr", ["reponse"])
    scorer.prompts.clear()
    sent = len(outbox.sent)

    load(db, queue, outbox, notice("B"))
    later = datetime.now(paris(TODAY, 8).tzinfo) + timedelta(days=40)
    load(
        db,
        queue,
        outbox,
        notice("A-RECT", notice_type="correction", corrects="A", deadline_at=later),
    )
    run_daily(db, outbox, paris(TODAY, 8))
    assert db.scalar(select(TenderMatch).where(TenderMatch.tender_id == tender_id(db, "B"))) is None
    assert scorer.prompts == []
    assert outbox.sent[sent:] == []  # no digest, no « Avis rectificatif »
    assert not any(s.startswith("Pilao —") for s, _ in mails_to(outbox, "user1@example.fr"))


def test_background_skips_without_reponse(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    doc = deposit(c).json()["id"]
    assert confirm(c, doc, valid_until=(TODAY + timedelta(days=25)).isoformat()).status_code == 200
    set_modules(db, "user1@example.fr", ["veille"])

    before = len(outbox.sent)
    run_daily(db, outbox, paris(TODAY, 6))
    assert outbox.sent[before:] == []  # no reminder about an attestation
