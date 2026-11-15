"""« Ce qu'il manque » (ADR-048): completing a missing item with the AI, one sentence."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.db.models import CreditEntry, CreditPrice, MarkerFill, MemoirSection
from app.domain.missing import marker_key
from app.services.stale_works import sweep_stale_works
from tests.api.helpers import signed_in_client
from tests.api.test_memoir import Factory
from tests.api.test_memoir_drafting import WriterModel, _user, latest
from tests.api.test_missing import drafted_bid, item
from tests.conftest import FakeQueue, Outbox

MARK = "[À COMPLÉTER : nombre d'agents affectés au site]"
KEY = marker_key("nombre d'agents affectés au site")
FILLED = "Équipe dédiée : 4 agents affectés au site."
Reply = dict[str, Any] | Callable[[str], dict[str, Any]]


class FillModel(WriterModel):
    """The writer of the chapters, plus the completion of one sentence."""

    def __init__(self) -> None:
        super().__init__()
        self.sentence = "."  # the marker is a sentence of its own
        self.fill_prompts: list[str] = []
        self.fill_reply: Reply = {"sentence": FILLED, "filled": True}
        self.fill_outage = False

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        user = _user(messages)
        if "<sentence>" in user:
            if self.fill_outage:
                raise ConnectionError("provider down")
            self.fill_prompts.append(str(messages[0]["content"]) + "\n" + user)
            reply = self.fill_reply
            out = reply(user) if callable(reply) else reply
            return json.dumps(out, ensure_ascii=False), 300, 40, 0.001
        return super().__call__(model, messages, max_tokens)


@pytest.fixture
def filler(monkeypatch: pytest.MonkeyPatch) -> FillModel:
    fake = FillModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(get_settings(), "llm_model_generation", "test/generation")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def with_staff(c: TestClient) -> None:
    res = c.post("/profile/human-resources", json={"qualification": "Agent de service", "count": 4})
    assert res.status_code == 201, res.text


def fill(c: TestClient, bid: str, key: str = KEY) -> Any:
    return c.post(f"/bids/{bid}/missing/fill", json={"key": key})


def test_fill_rewrites_only_the_unit(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    with_staff(c)
    res = fill(c, bid)
    assert res.status_code == 202, res.text
    assert item(c, bid, KEY)["fill"]["status"] == "pending"  # type: ignore[index]
    queue.drain_fills()
    assert filler.fill_prompts and all(MARK in p for p in filler.fill_prompts)
    assert all("Agent de service" in p for p in filler.fill_prompts)
    after = latest(c, memoir["id"])
    for old, new in zip(memoir["sections"], after["sections"], strict=True):
        assert new["content_md"] == old["content_md"].replace(MARK + ".", FILLED)
        assert new["edited_by_user"] is False
        [last, *_] = c.get(f"/memoir-sections/{new['id']}/revisions").json()
        assert last["origin"] == "generated"
        assert last["instruction"] == "Complété : nombre d'agents affectés au site"
    assert item(c, bid, KEY) is None


def test_fill_not_enough_keeps_the_text(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel
) -> None:
    filler.fill_reply = lambda user: {"sentence": MARK + ".", "filled": False}
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    after = latest(c, memoir["id"])
    assert [s["content_md"] for s in after["sections"]] == [
        s["content_md"] for s in memoir["sections"]
    ]
    assert [s["revision"] for s in after["sections"]] == [s["revision"] for s in memoir["sections"]]
    listed = item(c, bid, KEY)
    assert listed is not None and listed["fill"] == {
        "status": "done",
        "outcome": "not_enough",
        "error": None,
    }


def test_fill_refuses_an_invented_number(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel
) -> None:
    filler.fill_reply = {"sentence": "Équipe dédiée : 37 agents.", "filled": True}
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    with_staff(c)
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    assert MARK in latest(c, memoir["id"])["sections"][0]["content_md"]
    assert item(c, bid, KEY)["fill"]["outcome"] == "not_enough"  # type: ignore[index]


def test_fill_keeps_a_sentence_that_still_has_the_marker(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel
) -> None:
    filler.fill_reply = {"sentence": "Équipe : " + MARK + ".", "filled": True}
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    assert item(c, bid, KEY)["fill"]["outcome"] == "not_enough"  # type: ignore[index]


def test_chapter_edited_during_fill_is_left_alone(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    with_staff(c)
    first_id = memoir["sections"][0]["id"]
    calls: list[str] = []

    def edit_while_answering(user: str) -> dict[str, Any]:
        if not calls:  # the company edits the first chapter while the AI answers for it
            db.execute(
                update(MemoirSection)
                .where(MemoirSection.id == first_id)
                .values(
                    content_md=MemoirSection.content_md + "\n\nAjout de l'entreprise.",
                    revision=MemoirSection.revision + 1,
                )
            )
            db.commit()
        calls.append(user)
        return {"sentence": FILLED, "filled": True}

    filler.fill_reply = edit_while_answering
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    first, *others = latest(c, memoir["id"])["sections"]
    assert "Ajout de l'entreprise." in first["content_md"] and MARK in first["content_md"]
    assert all(MARK not in s["content_md"] and FILLED in s["content_md"] for s in others)
    listed = item(c, bid, KEY)
    assert listed is not None and [s["id"] for s in listed["sections"]] == [first_id]


def test_fill_is_free_by_default_and_refunded_when_priced(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)

    def fills() -> list[CreditEntry]:
        return list(
            db.scalars(
                select(CreditEntry)
                .where(CreditEntry.action == "marker_fill")
                .order_by(CreditEntry.at)
            )
        )

    filler.fill_reply = {"sentence": MARK + ".", "filled": False}  # the marker stays
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    assert fills() == []
    db.add(CreditPrice(action="marker_fill", credits=2))
    db.commit()
    filler.fill_outage = True
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    db.expire_all()
    entries = fills()
    assert [(e.kind, e.monthly + e.extra) for e in entries] == [("charge", -2), ("refund", 2)]
    assert item(c, bid, KEY)["fill"]["status"] == "error"  # type: ignore[index]


def test_fill_busy_or_unknown(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    res = fill(c, bid, "rien de tel")
    assert res.status_code == 404 and res.json()["error"]["code"] == "unknown_marker"
    db.execute(
        update(MemoirSection)
        .where(MemoirSection.id == memoir["sections"][0]["id"])
        .values(status="generating")
    )
    db.commit()
    res = fill(c, bid)
    assert res.status_code == 409 and res.json()["error"]["code"] == "memoir_busy"


# ---------- final review ------------------------------------------------------------------


def _price(db: Session, credits: int) -> None:
    db.add(CreditPrice(action="marker_fill", credits=credits))
    db.commit()


def _charges(db: Session) -> list[tuple[str, int]]:
    db.expire_all()
    return [
        (e.kind, e.monthly + e.extra)
        for e in db.scalars(
            select(CreditEntry).where(CreditEntry.action == "marker_fill").order_by(CreditEntry.at)
        )
    ]


def _left_for_dead(db: Session) -> None:
    db.execute(
        update(MarkerFill).values(
            status="running", updated_at=datetime.now(UTC) - timedelta(hours=1)
        )
    )
    db.commit()


def test_a_fill_left_running_is_closed_by_the_sweep_and_refunded(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)
    _price(db, 2)
    assert fill(c, bid).status_code == 202
    queue.pending_fills.clear()  # the worker died with it
    _left_for_dead(db)
    assert sweep_stale_works(db, queue) == 1
    assert _charges(db) == [("charge", -2), ("refund", 2)]
    assert item(c, bid, KEY)["fill"]["status"] == "error"  # type: ignore[index]
    assert sweep_stale_works(db, queue) == 0  # closed once


def test_a_dead_fill_does_not_block_a_new_one(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)
    with_staff(c)
    assert fill(c, bid).status_code == 202
    queue.pending_fills.clear()
    _left_for_dead(db)
    assert fill(c, bid).status_code == 202
    assert len(db.scalars(select(MarkerFill)).all()) == 2
    queue.drain_fills()
    assert item(c, bid, KEY) is None


def test_an_unexpected_error_fails_the_fill_and_refunds(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    filler: FillModel,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)
    _price(db, 2)
    assert fill(c, bid).status_code == 202

    def broken(*args: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.marker_fill.company_data", broken)
    queue.drain_fills()
    assert item(c, bid, KEY)["fill"]["status"] == "error"  # type: ignore[index]
    assert _charges(db) == [("charge", -2), ("refund", 2)]


def test_fill_refuses_a_small_invented_number(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel
) -> None:
    filler.fill_reply = {"sentence": "Équipe dédiée : 3 agents affectés au site.", "filled": True}
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)  # no staff in the profile: 3 comes from nowhere
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    assert MARK in latest(c, memoir["id"])["sections"][0]["content_md"]
    assert item(c, bid, KEY)["fill"]["outcome"] == "not_enough"  # type: ignore[index]


def test_fill_refuses_to_drop_another_marker(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, filler: FillModel
) -> None:
    filler.sentence = " encadrés par [À COMPLÉTER : nom du chef d'équipe]."
    filler.fill_reply = {
        "sentence": "4 agents affectés au site encadrés par un chef d'équipe expérimenté.",
        "filled": True,
    }
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    with_staff(c)
    assert fill(c, bid).status_code == 202
    queue.drain_fills()
    first = latest(c, memoir["id"])["sections"][0]["content_md"]
    assert MARK in first and "[À COMPLÉTER : nom du chef d'équipe]" in first
    assert item(c, bid, marker_key("nom du chef d'équipe")) is not None
