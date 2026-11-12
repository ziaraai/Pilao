"""Lot 4: the four paid actions take their credits and give them back when they fail (§3.3)."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.db.models import CreditEntry, CreditPrice, DceAnalysis, Organization, Plan, User
from app.services import credits
from app.services.jobs import set_job_status
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import DCE as ANALYSIS_DCE
from tests.api.test_bids import deposit, new_bid
from tests.api.test_memoir_drafting import WriterModel, add_knowledge, latest, prepared, section
from tests.api.test_profile_suggestions import FakeModel as ReaderModel
from tests.conftest import FakeQueue, Outbox

REAL_CREDITS = True
Factory = Callable[[], TestClient]


@pytest.fixture
def writer(monkeypatch: pytest.MonkeyPatch) -> WriterModel:
    fake = WriterModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(get_settings(), "llm_model_generation", "test/generation")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def org_of(db: Session, email: str = "user1@example.fr") -> Organization:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    db.expire_all()
    return db.get_one(Organization, user.org_id)


def top_up(db: Session, n: int, email: str = "user1@example.fr") -> None:
    db.add(CreditEntry(org_id=org_of(db, email).id, kind="grant", extra=n, reason="test"))
    db.commit()


def set_price(db: Session, action: str, n: int) -> None:
    row = db.get(CreditPrice, action)
    if row is None:
        db.add(CreditPrice(action=action, credits=n))
    else:
        row.credits = n
    db.commit()


def total(c: TestClient) -> int:
    return int(c.get("/credits").json()["total"])


def entries(db: Session, kind: str, action: str | None = None) -> list[CreditEntry]:
    db.expire_all()
    q = select(CreditEntry).where(CreditEntry.kind == kind)
    if action:
        q = q.where(CreditEntry.action == action)
    return list(db.scalars(q.order_by(CreditEntry.at)))


def deposited(c: TestClient, queue: FakeQueue) -> str:
    bid = new_bid(c)
    assert deposit(c, bid, ANALYSIS_DCE).status_code == 202
    queue.drain_dce()
    return bid


# ---------- analysis of the DCE -------------------------------------------------------------


def test_the_automatic_analysis_is_paid(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "ready"
    assert total(c) == 5
    [paid] = entries(db, "charge", "dce_analysis")
    assert (paid.monthly, paid.extra, str(paid.bid_id)) == (0, -2, bid)
    assert paid.user_id is not None  # whoever deposited the DCE
    line = c.get("/credits").json()["history"][0]
    assert (line["action_name"], line["credits"]) == ("Analyse du DCE", -2)


def test_a_rerun_is_paid_once_on_a_double_click(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)
    queue.drain_analyses()
    assert c.post(f"/bids/{bid}/analysis").status_code == 202
    assert c.post(f"/bids/{bid}/analysis").status_code == 409  # « Une analyse est déjà en cours. »
    assert len(entries(db, "charge", "dce_analysis")) == 2 and total(c) == 3


def test_a_failed_analysis_is_refunded_once(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)
    writer.reply = "pas du JSON"
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "error"
    assert total(c) == 7
    [back] = entries(db, "refund")
    assert back.reason == "Remboursé : l'analyse n'a pas abouti."

    analysis = db.scalar(select(DceAnalysis))
    assert analysis is not None
    set_job_status(db, "analyze_dce", analysis.id, "error", "encore")  # a second report
    db.commit()
    assert len(entries(db, "refund")) == 1


def test_the_automatic_analysis_waits_for_credits(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    set_price(db, "dce_analysis", 8)
    bid = deposited(c, queue)
    waiting = c.get(f"/bids/{bid}/analysis").json()
    assert waiting["status"] == "waiting_credits"
    assert waiting["error"] == "Analyse non lancée : crédits insuffisants."
    assert not queue.pending_analyses and entries(db, "charge") == []

    refused = c.post(f"/bids/{bid}/analysis")
    assert refused.status_code == 402
    assert refused.json()["error"]["message"] == (
        "Il faut 8 crédits, il vous en reste 7. Contactez Pilao."
    )
    top_up(db, 10)
    assert c.post(f"/bids/{bid}/analysis").status_code == 202
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "ready" and total(c) == 9


def test_a_free_action_writes_nothing(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    set_price(db, "dce_analysis", 0)
    deposited(c, queue)
    queue.drain_analyses()
    assert entries(db, "charge") == [] and total(c) == 7


def test_the_price_taken_is_the_price_given_back(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = deposited(c, queue)  # 2 taken
    set_price(db, "dce_analysis", 4)
    writer.reply = "pas du JSON"
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "error"
    [back] = entries(db, "refund")
    assert back.monthly + back.extra == 2 and total(c) == 7


def test_a_refund_after_the_month_ends_comes_back_as_extra(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    writer: WriterModel,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    org = org_of(db)
    org.plan_id = db.scalars(select(Plan.id).where(Plan.name == "Pilote")).one()
    db.commit()
    clock = {"now": datetime(2026, 11, 30, 12, tzinfo=UTC)}
    monkeypatch.setattr(credits, "_now", lambda: clock["now"])
    deposited(c, queue)  # 2 taken from November's credits
    [paid] = entries(db, "charge")
    assert (paid.monthly, paid.extra) == (-2, 0)

    clock["now"] = datetime(2026, 12, 1, 9, tzinfo=UTC)
    writer.reply = "pas du JSON"
    queue.drain_analyses()
    [back] = entries(db, "refund")
    assert (back.monthly, back.extra, back.month) == (0, 2, None)
    assert total(c) == 100 + 7 + 2  # December's credits, the welcome ones, the refund


def test_the_monthly_ai_ceiling_refunds_the_action(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    writer: WriterModel,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_eur_per_org", 0)
    bid = deposited(c, queue)
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "error"
    assert total(c) == 7 and len(entries(db, "refund")) == 1


# ---------- the memoir ----------------------------------------------------------------------


def test_drafting_is_paid_once_and_refunded_when_every_chapter_fails(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)  # the analysis took 2: 5 left
    writer.broken = {s["title"] for s in m["sections"]}
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 409  # already drafting
    assert len(entries(db, "charge", "memoir_generation")) == 1 and total(c) == 0
    queue.drain_memoir()
    assert all(s["status"] == "error" for s in latest(c, m["id"])["sections"])
    [back] = entries(db, "refund", "memoir_generation")
    assert back.reason == "Remboursé : la rédaction n'a pas abouti." and total(c) == 5


def test_a_failed_chapter_is_relaunched_for_free_a_ready_one_is_paid(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    top_up(db, 10)
    m = prepared(c, queue)
    writer.broken = {"1. Moyens"}
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    queue.drain_memoir()
    m = latest(c, m["id"])
    assert entries(db, "refund") == []  # one chapter is ready: the drafting stands
    before = total(c)

    writer.broken = set()
    broken = section(m, "1. Moyens")
    assert broken["relaunch_free"] is True  # what the button shows: « gratuit »
    assert section(m, "2. Méthodologie")["relaunch_free"] is False
    assert c.post(f"/memoir-sections/{broken['id']}/regenerate", json={}).status_code == 202
    queue.drain_memoir()
    assert total(c) == before and entries(db, "charge", "chapter_regeneration") == []

    ready = section(latest(c, m["id"]), "2. Méthodologie")
    assert c.post(f"/memoir-sections/{ready['id']}/regenerate", json={}).status_code == 202
    assert c.post(f"/memoir-sections/{ready['id']}/regenerate", json={}).status_code == 409
    assert len(entries(db, "charge", "chapter_regeneration")) == 1 and total(c) == before - 1


def test_a_failed_regeneration_is_refunded(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    top_up(db, 10)
    m = prepared(c, queue)
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    queue.drain_memoir()
    before = total(c)
    ready = section(latest(c, m["id"]), "2. Méthodologie")
    writer.broken = {"2. Méthodologie"}
    assert c.post(f"/memoir-sections/{ready['id']}/regenerate", json={}).status_code == 202
    queue.drain_memoir()
    [back] = entries(db, "refund", "chapter_regeneration")
    assert back.reason == "Remboursé : la régénération n'a pas abouti." and total(c) == before
    assert entries(db, "refund", "memoir_generation") == []  # the chapter had a text before


def test_a_relaunch_after_a_refunded_drafting_is_paid(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    """Every chapter failed: the drafting gave its 5 credits back, so a relaunch is paid —
    otherwise the memoir would be written chapter by chapter for nothing."""
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)  # 5 left
    writer.broken = {s["title"] for s in m["sections"]}
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    queue.drain_memoir()
    assert total(c) == 5  # refunded
    broken = section(latest(c, m["id"]), "1. Moyens")
    assert broken["status"] == "error" and broken["relaunch_free"] is False

    writer.broken = set()
    assert c.post(f"/memoir-sections/{broken['id']}/regenerate", json={}).status_code == 202
    assert len(entries(db, "charge", "chapter_regeneration")) == 1 and total(c) == 4


def test_a_relaunch_after_a_refunded_regeneration_is_paid(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    top_up(db, 10)
    m = prepared(c, queue)
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    queue.drain_memoir()
    ready = section(latest(c, m["id"]), "2. Méthodologie")
    writer.broken = {"2. Méthodologie"}
    assert c.post(f"/memoir-sections/{ready['id']}/regenerate", json={}).status_code == 202
    queue.drain_memoir()  # failed: its credit came back
    before = total(c)
    failed = section(latest(c, m["id"]), "2. Méthodologie")
    assert failed["status"] == "error" and failed["relaunch_free"] is False

    writer.broken = set()
    assert c.post(f"/memoir-sections/{ready['id']}/regenerate", json={}).status_code == 202
    assert len(entries(db, "charge", "chapter_regeneration")) == 2 and total(c) == before - 1


# ---------- reading the documents for the profile -------------------------------------------


def _read_ready(c: TestClient, queue: FakeQueue, monkeypatch: pytest.MonkeyPatch) -> ReaderModel:
    fake = ReaderModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    add_knowledge(c, queue, "Mémoire 2025", "Nous employons 12 agents de service.")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def test_reading_the_documents_is_paid_once(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    _read_ready(c, queue, monkeypatch)
    assert c.post("/profile/suggestions/read").status_code == 202
    assert (
        c.post("/profile/suggestions/read").status_code == 409
    )  # « Une lecture est déjà en cours. »
    queue.drain_profile_prefill()
    [paid] = entries(db, "charge", "profile_prefill")
    assert paid.extra == -1 and total(c) == 6


def test_a_failed_reading_is_refunded(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    _read_ready(c, queue, monkeypatch)
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_eur_per_org", 0)
    assert c.post("/profile/suggestions/read").status_code == 202
    queue.drain_profile_prefill()
    [back] = entries(db, "refund", "profile_prefill")
    assert back.reason == "Remboursé : la lecture n'a pas abouti." and total(c) == 7


def test_without_credits_nothing_is_launched(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    writer: WriterModel,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)  # 5 left
    set_price(db, "memoir_generation", 6)
    res = c.post(f"/memoirs/{m['id']}/generate")
    assert res.status_code == 402 and res.json()["error"]["code"] == "credits_exhausted"
    assert latest(c, m["id"])["status"] == "draft" and not queue.pending_sections
    set_price(db, "profile_prefill", 6)
    _read_ready(c, queue, monkeypatch)
    assert c.post("/profile/suggestions/read").status_code == 402


def test_a_reading_the_queue_never_took_is_refunded(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    _read_ready(c, queue, monkeypatch)
    queue.down = True
    assert c.post("/profile/suggestions/read").status_code == 202
    assert c.get("/profile/suggestions").json()["job"]["status"] == "error"
    [back] = entries(db, "refund", "profile_prefill")
    assert back.reason == "Remboursé : la lecture n'a pas abouti." and total(c) == 7


def test_a_reading_retried_by_the_queue_is_paid_once(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import profile_prefill

    c = signed_in_client(make_client, outbox)
    _read_ready(c, queue, monkeypatch)
    real = profile_prefill.document_blocks
    monkeypatch.setattr(profile_prefill, "document_blocks", _fails_once(real))
    monkeypatch.setattr(profile_prefill, "will_retry", lambda: True)  # RQ runs it again
    assert c.post("/profile/suggestions/read").status_code == 202
    org_id = list(queue.pending_prefill)
    with pytest.raises(RuntimeError):
        queue.drain_profile_prefill()
    assert c.get("/profile/suggestions").json()["job"]["status"] == "pending"  # still waiting
    assert entries(db, "refund") == [] and total(c) == 6

    queue.pending_prefill = org_id  # the retry, which succeeds
    queue.drain_profile_prefill()
    assert c.get("/profile/suggestions").json()["job"]["status"] == "done"
    assert entries(db, "refund") == [] and total(c) == 6  # paid once, for a reading made


def _fails_once(real: Callable[..., object]) -> Callable[..., object]:
    calls: list[int] = []

    def blocks(*args: object) -> object:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("disk unplugged")
        return real(*args)

    return blocks
