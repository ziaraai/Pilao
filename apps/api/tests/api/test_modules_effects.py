"""What follows a company's modules (lot 3, spec §3.2, §3.3, §5.3)."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bid, TenderMatch
from app.services.alerts import run_daily
from tests.api.helpers import signed_in_client
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
    # no digest; the « Avis rectificatif » still comes: it changes a dossier being answered
    # (deadline, documents), which belongs to « Réponse », not to the watch
    [mail] = outbox.sent[sent:]
    assert mail.subject.startswith("Avis rectificatif")
    assert "Vérifiez votre dossier dans Pilao." in mail.body
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


def test_profile_without_the_watch_asks_nothing_of_it(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    """The CPV codes, keywords and departments are hidden without « Veille » (spec §3.2): the
    profile no longer asks for them, so it can reach 100 % and « Pour bien démarrer » ends."""
    c = signed_in_client(make_client, outbox)
    c.put("/profile", json={"trades": ["vitrerie"]})
    with_watch = c.get("/profile/completeness").json()
    assert "watch" in with_watch["missing_keys"] and "departments" in with_watch["missing_keys"]

    set_modules(db, "user1@example.fr", ["reponse"])
    without = c.get("/profile/completeness").json()
    assert "watch" not in without["missing_keys"]
    assert "departments" not in without["missing_keys"]
    assert without["pct"] == with_watch["pct"] + 15 + 10


def test_reminders_reach_a_company_with_reponse_only(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    """Final review, finding 1: the attestation reminders belong to « Réponse », not to the
    watch (spec §3.3): a company without « Veille » still gets them."""
    c = company(make_client, outbox, queue)
    doc = deposit(c).json()["id"]
    assert confirm(c, doc, valid_until=(TODAY + timedelta(days=25)).isoformat()).status_code == 200
    set_modules(db, "user1@example.fr", ["reponse"])

    before = len(outbox.sent)
    run_daily(db, outbox, paris(TODAY, 6))
    assert [m.to for m in outbox.sent[before:]] == ["user1@example.fr"]


def test_profile_change_matches_nothing_without_veille(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    """Final review, finding 2: saving the trades without « Veille » (or enabling the watch of a
    suspended company) re-matches the open notices: no match may be created (spec §3.3)."""
    from app.services.tenders import rematch_org
    from tests.api.test_suspension import suspend

    c = signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", ["reponse"])
    load(db, queue, outbox, notice("A"))
    assert (
        c.put(
            "/profile",
            json={"trades": ["nettoyage_locaux"], "departments": ["69"], "cpv_codes": ["90911200"]},
        ).status_code
        == 200
    )
    queue.drain_tenders()
    assert db.scalar(select(TenderMatch)) is None

    set_modules(db, "user1@example.fr", ["veille", "reponse"])
    org = suspend(db, "user1@example.fr")
    rematch_org(db, org.id, queue)
    assert db.scalar(select(TenderMatch)) is None


def test_followed_without_bid_can_be_dismissed(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    """Final review, finding 3: a notice followed without a bid (no « Réponse ») is not stuck:
    « Écarter » works; a notice followed with a bid still asks to delete the bid first."""
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"), notice("B"))
    with_bid = tender_id(db, "B")
    assert c.post(f"/tenders/{with_bid}/track").json()["bid"] is not None
    set_modules(db, "user1@example.fr", ["veille"])
    a = tender_id(db, "A")
    assert c.post(f"/tenders/{a}/track").json() == {"bid": None}

    res = c.post(f"/tenders/{a}/dismiss", json={"reason": "Suivie par erreur"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "dismissed"
    refused = c.post(f"/tenders/{with_bid}/dismiss", json={"reason": "x"})
    assert refused.json()["error"]["code"] == "tender_tracked"  # its bid is kept, untouched


def test_correction_without_a_dossier_points_to_the_notice(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    """A company following a notice without « Réponse » has no dossier: the « Avis
    rectificatif » e-mail sends it to the notice, not to a dossier that does not exist."""
    c = company(make_client, outbox, queue)
    set_modules(db, "user1@example.fr", ["veille"])
    load(db, queue, outbox, notice("A"))
    assert c.post(f"/tenders/{tender_id(db, 'A')}/track").json() == {"bid": None}
    sent = len(outbox.sent)

    later = datetime.now(paris(TODAY, 8).tzinfo) + timedelta(days=40)
    load(
        db,
        queue,
        outbox,
        notice("A-RECT", notice_type="correction", corrects="A", deadline_at=later),
    )
    [mail] = outbox.sent[sent:]
    assert mail.subject.startswith("Avis rectificatif")
    assert "Consultez l'annonce dans Pilao." in mail.body
    assert "dossier" not in mail.body
