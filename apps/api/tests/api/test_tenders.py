"""The watch: import, pre-filter, AI score, list, actions (US-2.1 to US-2.3)."""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.db.models import AiCall, Tender, TenderMatch
from app.schemas.tenders import TenderIn
from app.services.tenders import ingest
from tests.api.helpers import signed_in_client
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]
NOW = datetime.now(UTC)


class ScoreModel:
    """Scores from the notice title written in the prompt."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.scores: dict[str, int] = {}
        self.reply: str | None = None

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        user = str(messages[1]["content"])
        self.prompts.append(user)
        if self.reply is not None:
            return self.reply, 300, 10, 0.001
        title = user.split("Objet : ", 1)[1].split("\n", 1)[0]
        score = self.scores.get(title, 70)
        answer = {"score": score, "explanation": f"Score de « {title} ».", "relevant_lots": []}
        return json.dumps(answer), 300, 40, 0.001


@pytest.fixture
def scorer(monkeypatch: pytest.MonkeyPatch) -> ScoreModel:
    fake = ScoreModel()
    monkeypatch.setattr(get_settings(), "llm_model_scoring", "test/scoring")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def notice(source_id: str, **kw: Any) -> TenderIn:
    base: dict[str, Any] = {
        "source": "boamp",
        "source_id": source_id,
        "title": f"Nettoyage {source_id}",
        "buyer_name": "Ville de Lyon",
        "procedure": "Procédure adaptée",
        "cpv_codes": ["90911200"],
        "departments": ["69"],
        "estimated_amount_eur": 120_000,
        "published_at": NOW - timedelta(days=1),
        "deadline_at": NOW + timedelta(days=20),
        "notice_url": f"https://www.boamp.fr/avis/{source_id}",
    }
    return TenderIn.model_validate({**base, **kw})


PROFILE = {
    "cpv_codes": ["90910000"],
    "keywords_include": ["nettoyage"],
    "keywords_exclude": ["désamiantage"],
    "departments": ["69", "01"],
    "min_amount_cents": 2_000_000,
    "max_amount_cents": 50_000_000,
}


def company(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, n: int = 1, **profile: Any
) -> TestClient:
    c = signed_in_client(make_client, outbox, n)
    assert c.put("/profile", json={**PROFILE, **profile}).status_code == 200
    queue.drain_tenders()
    return c


def load(db: Session, queue: FakeQueue, outbox: Outbox, *items: TenderIn) -> Any:
    report = ingest(db, list(items), outbox)
    if report.to_match:
        queue.enqueue_match_tenders(report.to_match)
    queue.drain_tenders()
    return report


def titles(c: TestClient, **params: Any) -> list[str]:
    res = c.get("/tenders", params=params)
    assert res.status_code == 200, res.text
    return [t["title"] for t in res.json()["items"]]


def tender_id(db: Session, source_id: str) -> str:
    return str(db.scalar(select(Tender.id).where(Tender.source_id == source_id)))


def test_matching_notices_are_scored_and_sorted(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    scorer.scores = {"Nettoyage A": 90, "Nettoyage B": 90, "Nettoyage C": 40}
    report = load(
        db,
        queue,
        outbox,
        notice("A", deadline_at=NOW + timedelta(days=30)),
        notice("B", deadline_at=NOW + timedelta(days=10), departments=["01"]),
        notice("C", procedure="Appel d'offres ouvert"),
        notice("D", departments=["75"]),  # out of the company's area
        notice("E", deadline_at=NOW - timedelta(hours=1)),  # closed
        notice("F", notice_type="award"),  # stored for V2, never in the watch (CA3)
        notice("G", description="Lot 3 : désamiantage"),  # excluded keyword
        notice("H", estimated_amount_eur=900_000),  # above the company's maximum
    )
    assert (report.created, report.awards) == (8, 1)
    # Score first, then the nearest deadline (CA3).
    assert titles(c) == ["Nettoyage B", "Nettoyage A", "Nettoyage C"]
    first = c.get("/tenders").json()["items"][0]
    assert first["score"] == 90 and first["explanation"] == "Score de « Nettoyage B »."
    assert first["reasons"] == ["code CPV 90911200", "mot-clé « nettoyage »", "département 01"]
    assert first["notice_url"] == "https://www.boamp.fr/avis/B"
    calls = db.scalars(select(AiCall).where(AiCall.task == "tender_scoring")).all()
    assert len(calls) == 3  # only the pre-filtered notices are scored (docs/08)
    prompt = next(p for p in scorer.prompts if "Objet : Nettoyage B" in p)
    assert "Zones : 69, 01" in prompt and "Montants visés : 20 000 à 500 000 € HT" in prompt
    assert "Lieu : 01" in prompt and "Acheteur : Ville de Lyon" in prompt

    # Filters (CA4)
    assert titles(c, min_score=50) == ["Nettoyage B", "Nettoyage A"]
    assert titles(c, department="01") == ["Nettoyage B"]
    assert titles(c, procedure="Appel d'offres ouvert") == ["Nettoyage C"]
    assert titles(c, deadline_before=(NOW + timedelta(days=15)).date().isoformat()) == [
        "Nettoyage B"
    ]
    assert titles(c, q="nettoyage a") == ["Nettoyage A"]
    assert titles(c, trade="vitrerie") == []  # 90911300 is not 90911200
    assert titles(c, trade="nettoyage_locaux") == ["Nettoyage B", "Nettoyage A", "Nettoyage C"]
    listing = c.get("/tenders").json()
    assert listing["departments"] == ["01", "69"] and listing["total"] == 3
    assert listing["procedures"] == ["Appel d'offres ouvert", "Procédure adaptée"]


def test_each_company_sees_only_its_own_matches(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    a = company(make_client, outbox, queue, 1)
    b = company(make_client, outbox, queue, 2, departments=["75"], keywords_include=["gardiennage"])
    load(db, queue, outbox, notice("A"), notice("P", departments=["75"]))
    assert titles(a) == ["Nettoyage A"] and titles(b) == ["Nettoyage P"]
    assert b.get(f"/tenders/{tender_id(db, 'A')}").status_code == 404
    assert b.post(f"/tenders/{tender_id(db, 'A')}/track").status_code == 404
    b_prompts = [p for p in scorer.prompts if "Zones : 75" in p]
    assert b_prompts and all("Zones : 69" not in p for p in b_prompts)
    assert all("gardiennage" not in p for p in scorer.prompts if "Zones : 69" in p)


def test_tracking_creates_a_bid_and_dismissing_keeps_the_reason(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A", buyer_name="Ville de Lyon"), notice("B"))
    a = tender_id(db, "A")
    res = c.post(f"/tenders/{a}/track")
    assert res.status_code == 201
    bid = res.json()["bid"]  # TrackOut (lot 3): the bid, with « Réponse aux appels d'offres »
    assert bid["title"] == "Nettoyage A" and bid["status"] == "to_review"
    assert bid["buyer_name"] == "Ville de Lyon"
    assert c.post(f"/tenders/{a}/track").json()["bid"]["id"] == bid["id"]  # idempotent
    assert titles(c) == ["Nettoyage B"] and titles(c, status="tracked") == ["Nettoyage A"]
    assert c.get(f"/tenders/{a}").json()["bid_id"] == bid["id"]
    refused = c.post(f"/tenders/{a}/dismiss", json={"reason": "trop loin"})
    assert refused.json()["error"]["code"] == "tender_tracked"

    b = tender_id(db, "B")
    dismissed = c.post(f"/tenders/{b}/dismiss", json={"reason": "Trop gros pour nous"}).json()
    assert (
        dismissed["status"] == "dismissed" and dismissed["dismiss_reason"] == "Trop gros pour nous"
    )
    assert titles(c) == [] and titles(c, status="dismissed") == ["Nettoyage B"]
    assert c.post(f"/tenders/{b}/dismiss", json={"reason": " "}).status_code == 422
    assert c.post(f"/tenders/{b}/restore").json()["status"] == "new"

    assert c.delete(f"/bids/{bid['id']}").status_code == 204
    back = c.get(f"/tenders/{a}").json()
    assert back["status"] == "new" and back["bid_id"] is None  # the notice returns to the list


def test_a_correction_updates_the_notice_and_warns_who_follows_it(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"), notice("B"))
    a, b = tender_id(db, "A"), tender_id(db, "B")
    bid_a = c.post(f"/tenders/{a}/track").json()["bid"]
    bid_b = c.post(f"/tenders/{b}/track").json()["bid"]
    own_date = (NOW + timedelta(days=5)).isoformat()
    c.patch(f"/bids/{bid_b['id']}", json={"deadline_at": own_date})  # the user's own date
    sent = len(outbox.sent)

    later = NOW + timedelta(days=40)
    correction = notice(
        "A-RECT", notice_type="correction", corrects="A", title="Nettoyage A", deadline_at=later
    )
    report = load(db, queue, outbox, correction)
    assert report.corrected == 1 and report.created == 0
    tender = c.get(f"/tenders/{a}").json()
    assert datetime.fromisoformat(tender["deadline_at"]) == later
    assert list(tender["corrections"][0]["changes"]) == ["date limite"]
    assert datetime.fromisoformat(c.get(f"/bids/{bid_a['id']}").json()["deadline_at"]) == later
    mails = outbox.sent[sent:]
    assert len(mails) == 1 and mails[0].subject == "Avis rectificatif : Nettoyage A"
    assert "date limite" in mails[0].body
    assert "Vérifiez votre dossier dans Pilao." in mails[0].body  # followed with a dossier
    assert load(db, queue, outbox, correction).unchanged == 1 and len(outbox.sent) == sent + 1

    load(
        db,
        queue,
        outbox,
        notice(
            "B-RECT", notice_type="correction", corrects="B", title="Nettoyage B", deadline_at=later
        ),
    )
    kept = c.get(f"/bids/{bid_b['id']}").json()["deadline_at"]
    assert datetime.fromisoformat(kept) == datetime.fromisoformat(own_date)


def test_the_same_contract_on_boamp_and_ted_is_listed_once(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    deadline = NOW + timedelta(days=25)
    load(
        db,
        queue,
        outbox,
        notice("A", title="Nettoyage des locaux de la mairie", deadline_at=deadline),
    )
    ted = notice(
        "2026/S 210-123456",
        source="ted",
        title="Mairie — nettoyage des locaux",
        buyer_name="VILLE DE LYON",
        deadline_at=deadline + timedelta(hours=2),
    )
    report = load(db, queue, outbox, ted)
    assert report.duplicates == 1
    duplicate = db.scalar(select(Tender).where(Tender.source == "ted"))
    assert duplicate is not None and str(duplicate.duplicate_of) == tender_id(db, "A")
    assert titles(c) == ["Nettoyage des locaux de la mairie"]


def test_a_notice_published_again_is_updated_not_duplicated(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"))
    assert load(db, queue, outbox, notice("A")).unchanged == 1
    assert load(db, queue, outbox, notice("A", title="Nettoyage A (modifié)")).updated == 1
    assert db.scalar(select(Tender.title).where(Tender.source_id == "A")) == "Nettoyage A (modifié)"
    assert len(db.scalars(select(TenderMatch)).all()) == 1


def test_a_notice_completed_later_is_scored_again(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    """A notice read again with more details (description, amount) gets a new score; one
    that no longer fits leaves the list; a followed one is left alone."""
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"), notice("B"), notice("T"))
    c.post(f"/tenders/{tender_id(db, 'T')}/track")
    first = len(scorer.prompts)
    scorer.scores = {"Nettoyage A": 91}
    load(
        db,
        queue,
        outbox,
        notice("A", description="Nettoyage quotidien de 12 écoles"),
        notice("B", departments=["75"]),  # moved out of the company's area
        notice("T", description="Plus de détails"),
    )
    assert c.get(f"/tenders/{tender_id(db, 'A')}").json()["score"] == 91
    assert len(scorer.prompts) == first + 1  # A only: B left, T is followed
    assert "Nettoyage quotidien de 12 écoles" in scorer.prompts[-1]
    assert titles(c) == ["Nettoyage A"] and titles(c, status="tracked") == ["Nettoyage T"]


def test_a_profile_change_filters_and_scores_again(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, notice("A"), notice("B"), notice("P", departments=["75"]))
    c.post(f"/tenders/{tender_id(db, 'A')}/track")
    scorer.scores = {"Nettoyage P": 85}
    assert c.put("/profile", json={**PROFILE, "departments": ["75"]}).status_code == 200
    queue.drain_tenders()
    assert titles(c) == ["Nettoyage P"]  # B left the scope; P entered it
    assert c.get(f"/tenders/{tender_id(db, 'P')}").json()["score"] == 85
    assert titles(c, status="tracked") == ["Nettoyage A"]  # a followed notice is kept


def test_scoring_problems_never_hide_a_notice(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = company(make_client, outbox, queue)
    scorer.reply = "pas du JSON"
    load(db, queue, outbox, notice("A"))
    item = c.get("/tenders").json()["items"][0]
    assert item["score"] is None and item["score_error"] == (
        "Le modèle n'a pas produit de réponse exploitable."
    )
    monkeypatch.setattr(get_settings(), "llm_model_scoring", "")  # no model configured
    load(db, queue, outbox, notice("B"))
    b = c.get(f"/tenders/{tender_id(db, 'B')}").json()
    assert b["score"] is None and b["score_error"] is None  # scored once a model is set
    assert sorted(titles(c)) == ["Nettoyage A", "Nettoyage B"]  # both still listed


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/tenders").status_code == 401
    assert anon.post(f"/tenders/{uuid.uuid4()}/track").status_code == 401


def test_links_must_be_web_links_and_dates_without_zone_are_paris_time() -> None:
    item = notice(
        "X",
        notice_url="javascript:alert(document.cookie)",
        documents_url=" https://marches.example.fr/dce/123 ",
        deadline_at="2026-12-15T12:00:00",
    )
    assert item.notice_url is None  # never rendered as a link
    assert item.documents_url == "https://marches.example.fr/dce/123"
    assert item.deadline_at is not None and item.deadline_at.utcoffset() == timedelta(hours=1)


def test_every_notice_is_scored_even_beyond_one_batch(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import tenders as svc

    monkeypatch.setattr(svc, "SCORE_BATCH", 2)
    c = company(make_client, outbox, queue)
    load(db, queue, outbox, *(notice(f"N{i}") for i in range(5)))
    items = c.get("/tenders").json()["items"]
    assert len(items) == 5 and all(t["score"] == 70 for t in items)
    assert len(scorer.prompts) == 5  # each notice paid once


def test_a_notice_being_scored_by_another_job_is_left_to_it(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scorer: ScoreModel, db: Session
) -> None:
    from sqlalchemy import update

    from app.services.tenders import CLAIM_TIMEOUT, match_tenders

    c = company(make_client, outbox, queue)
    report = ingest(db, [notice("A"), notice("B")], outbox)
    match_tenders(db, report.to_match, queue)  # matched; their scoring job is queued
    a, b = tender_id(db, "A"), tender_id(db, "B")
    db.execute(  # A: claimed just now by a running job; B: by a job killed long ago
        update(TenderMatch).where(TenderMatch.tender_id == uuid.UUID(a)).values(scored_at=NOW)
    )
    db.execute(
        update(TenderMatch)
        .where(TenderMatch.tender_id == uuid.UUID(b))
        .values(scored_at=NOW - CLAIM_TIMEOUT - timedelta(minutes=1))
    )
    db.commit()
    queue.drain_tenders()
    assert c.get(f"/tenders/{a}").json()["score"] is None
    assert c.get(f"/tenders/{b}").json()["score"] == 70
