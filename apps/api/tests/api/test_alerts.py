"""Daily e-mails (US-2.4, US-5.2), the hourly schedule, and the dashboard (US-5.3, US-5.4)."""

import importlib
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from croniter import croniter
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exports.dc_forms import french_date
from app.services.alerts import run_daily
from tests.api.helpers import signed_in_client
from tests.api.test_tenders import (  # noqa: F401 - the scorer fixture
    PROFILE,
    Factory,
    ScoreModel,
    company,
    load,
    notice,
    scorer,
    tender_id,
)
from tests.api.test_vault import TODAY, confirm, day, deposit
from tests.conftest import FakeQueue, Outbox

PARIS = ZoneInfo("Europe/Paris")


def paris(d: date, hour: int) -> datetime:
    return datetime.combine(d, time(hour), PARIS)


def mails_to(outbox: Outbox, email: str) -> list[tuple[str, str]]:
    return [(m.subject, m.body) for m in outbox.sent if m.to == email]


def test_the_morning_digest_lists_new_notices_above_the_threshold_once(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue, min_score_alert=60)
    other = company(make_client, outbox, queue, 2, departments=["75"])
    scorer.scores = {"Nettoyage A": 85, "Nettoyage B": 40, "Nettoyage C": 70, "Nettoyage T": 95}
    load(db, queue, outbox, notice("A"), notice("B"), notice("C"), notice("T"))
    c.post(f"/tenders/{tender_id(db, 'T')}/track")  # already followed: not in the e-mail
    today = datetime.now(PARIS).date()

    assert run_daily(db, outbox, paris(today, 6)).digests == 0  # too early
    report = run_daily(db, outbox, paris(today, 8))
    assert report.digests == 1  # the other company has no notice in its area
    [(subject, body)] = mails_to(outbox, "user1@example.fr")[-1:]
    assert subject == "Pilao — 2 nouvelles annonces pour vous"
    assert body.index("85/100 — Nettoyage A") < body.index("70/100 — Nettoyage C")
    assert "Nettoyage B" not in body and "Nettoyage T" not in body
    assert "(score de 60 ou plus)" in body and "http://localhost:3000/annonces" in body
    assert not any(s.startswith("Pilao —") for s, _ in mails_to(outbox, "user2@example.fr"))

    sent = len(outbox.sent)
    scorer.scores["Nettoyage D"] = 90
    load(db, queue, outbox, notice("D"))
    run_daily(db, outbox, paris(today, 9))
    assert len(outbox.sent) == sent  # once a day
    run_daily(db, outbox, paris(today + timedelta(days=1), 8))
    [(subject, body)] = mails_to(outbox, "user1@example.fr")[-1:]
    assert subject == "Pilao — 1 nouvelle annonce pour vous"
    assert "Nettoyage D" in body and "Nettoyage A" not in body  # each notice is sent once
    assert other.get("/tenders").json()["total"] == 0


def test_attestations_are_announced_at_30_and_7_days_then_once_expired(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the hourly run also purges expired sessions: this one must outlive the 31 days below
    monkeypatch.setattr(get_settings(), "session_ttl_hours", 24 * 60)
    c = signed_in_client(make_client, outbox)
    doc = deposit(c).json()["id"]
    confirm(c, doc, valid_until=day(25))
    deposit(c)  # never confirmed: no alert about it

    def subjects_on(offset: int) -> list[str]:
        before = len(outbox.sent)
        run_daily(db, outbox, paris(TODAY + timedelta(days=offset), 6))
        return [m.subject for m in outbox.sent[before:]]

    soon = "Attestation à renouveler : Attestation de vigilance URSSAF (fin le " + (
        f"{french_date(TODAY + timedelta(days=25))})"
    )
    assert subjects_on(0) == [soon]  # 25 days left: the 30-day alert
    assert subjects_on(1) == []  # once per threshold
    assert subjects_on(19) == [soon]  # 6 days left: the 7-day alert
    assert subjects_on(20) == []
    assert subjects_on(26) == ["Attestation expirée : Attestation de vigilance URSSAF"]
    assert subjects_on(27) == []
    body = outbox.sent[-1].body
    assert "n'est plus jointe à vos exports" in body and "/coffre-fort" in body
    old = deposit(c).json()["id"]
    confirm(c, old, valid_until=day(-40))  # expired long before Pilao: no e-mail about it
    assert subjects_on(0) == []
    confirm(c, doc, valid_until=day(60))  # renewed: its new end date is watched again
    renewed = "Attestation à renouveler : Attestation de vigilance URSSAF (fin le " + (
        f"{french_date(TODAY + timedelta(days=60))})"
    )
    assert subjects_on(31) == [renewed]


def test_the_alerts_and_the_notice_import_are_scheduled() -> None:
    from rq import cron

    module = importlib.import_module("app.workers.cron")
    cron._job_data_registry.clear()
    importlib.reload(module)  # what `rq cron app/workers/cron.py` loads
    jobs = {job["func"].__name__: job for job in cron._job_data_registry}
    assert set(jobs) == {
        "daily_alerts_job",
        "import_tenders_job",
        "sweep_stale_works_job",
        "watch_dces_job",  # the DCE retrieved by the robot, every morning
    }
    assert jobs["sweep_stale_works_job"]["cron"] == "*/15 * * * *"  # lot 4: dead works refunded
    assert {job["queue_name"] for job in jobs.values()} == {"default"}
    start = datetime(2026, 11, 5, 7, 0)
    alerts = croniter(jobs["daily_alerts_job"]["cron"], start)
    assert alerts.get_next(datetime) == datetime(2026, 11, 5, 7, 5)  # every hour, at :05
    notices = croniter(jobs["import_tenders_job"]["cron"], start)
    assert [notices.get_next(datetime) for _ in range(2)] == [
        datetime(2026, 11, 5, 8, 20),  # every 2 hours, at :20
        datetime(2026, 11, 5, 10, 20),
    ]


def test_dashboard_says_what_to_do_then_notices_bids_and_results(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    c = company(make_client, outbox, queue)
    assert c.get("/dashboard").json()["tenders_connected"] is False  # no notice loaded yet
    scorer.scores = {"Nettoyage A": 90, "Nettoyage B": 50}
    load(db, queue, outbox, notice("A"), notice("B"), notice("C"), notice("D"))
    soon = c.post(
        "/bids",
        json={
            "title": "Gymnase",
            "deadline_at": (datetime.now(PARIS) + timedelta(days=4)).isoformat(),
        },
    ).json()
    later = c.post(
        "/bids",
        json={
            "title": "Piscine",
            "deadline_at": (datetime.now(PARIS) + timedelta(days=30)).isoformat(),
        },
    ).json()
    for title, status, amount in (
        ("Écoles", "won", 4_500_000),
        ("Crèche", "lost", None),
        ("Mairie", "won", None),
    ):
        bid = c.post("/bids", json={"title": title}).json()
        change = {"status": status, "submitted_amount_cents": amount}
        assert c.patch(f"/bids/{bid['id']}", json=change).status_code == 200
    result = c.patch(
        f"/bids/{later['id']}",
        json={
            "status": "submitted",
            "submitted_amount_cents": 9_800_000,
            "result_notes": "Technique 52/60",
        },
    ).json()
    assert result["submitted_amount_cents"] == 9_800_000  # US-5.4
    urssaf = deposit(c).json()["id"]
    confirm(c, urssaf, valid_until=day(12))

    board = c.get("/dashboard").json()
    assert board["new_tenders"] == 4 and board["tenders_connected"] is True
    best = board["best_tenders"]
    assert [t["score"] for t in best] == [90, 70, 70] and best[0]["title"] == "Nettoyage A"
    # what to do now: the near deadline first, then the attestation to renew
    assert [(a["level"], a["title"], a["href"]) for a in board["actions"]] == [
        ("soon", "Date limite dans 4 jours — Gymnase", f"/dossiers/{soon['id']}"),
        ("soon", "Document à renouveler — Attestation de vigilance URSSAF", "/coffre-fort"),
    ]
    assert board["actions"][0]["detail"] == "Prochaine étape : déposer le DCE."
    # the bids followed: in progress, then the offer awaiting its result
    assert [(b["title"], b["done"], b["next_step"]) for b in board["bids"]] == [
        ("Gymnase", [], "Déposer le DCE"),
        ("Piscine", ["submitted"], None),
    ]
    steps = {s["key"]: s["done"] for s in board["getting_started"]}
    assert steps["vault"] is False and steps["knowledge"] is False and steps["bid"] is True
    assert board["results"] == {
        "deposited": 4,
        "won": 2,
        "lost": 1,
        "submitted": 1,
        "success_rate": 0.67,
        "amount_won_cents": 4_500_000,
    }

    # another company sees none of it
    other = company(make_client, outbox, queue, 2).get("/dashboard").json()
    assert other["actions"] == [] and other["bids"] == []
    assert other["results"]["deposited"] == 0 and other["results"]["amount_won_cents"] == 0
    assert [s["done"] for s in other["getting_started"]] == [False, False, False, False]


def test_dashboard_requires_authentication(make_client: Factory) -> None:
    assert make_client().get("/dashboard").status_code == 401
