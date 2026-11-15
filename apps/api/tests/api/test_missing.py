"""« Ce qu'il manque » (ADR-048): the list, answering in place, removing, the DC1/DC2."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import MemoirSection
from app.domain.missing import marker_key
from tests.api.helpers import signed_in_client
from tests.api.test_memoir import Factory, analyzed_bid
from tests.api.test_memoir_drafting import (  # noqa: F401
    WriterModel,
    latest,
    model,
    quote_everything,
)
from tests.conftest import FakeQueue, Outbox


@pytest.fixture
def writer(model: WriterModel) -> WriterModel:  # noqa: F811
    return model


MARK = "[À COMPLÉTER : nombre d'agents affectés au site]"
KEY = marker_key("nombre d'agents affectés au site")


def drafted_bid(c: TestClient, queue: FakeQueue) -> tuple[str, dict[str, Any]]:
    bid = analyzed_bid(c, queue)
    m = c.post(f"/bids/{bid}/memoir").json()
    assert c.post(f"/memoirs/{m['id']}/generate").status_code == 202
    queue.drain_memoir()
    return bid, latest(c, m["id"])


def missing(c: TestClient, bid: str) -> dict[str, Any]:
    res = c.get(f"/bids/{bid}/missing")
    assert res.status_code == 200, res.text
    return dict(res.json())


def item(c: TestClient, bid: str, key: str) -> dict[str, Any] | None:
    return next((i for i in missing(c, bid)["items"] if i["key"] == key), None)


def test_markers_grouped_across_chapters(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    out = missing(c, bid)
    assert out["memoir_id"] == memoir["id"] and out["memoir_busy"] is False
    found = item(c, bid, KEY)
    assert found is not None
    assert found["text"] == "nombre d'agents affectés au site"
    assert found["kind"] == "staff"  # the keywords: the fake model gives no drawer
    assert [s["id"] for s in found["sections"]] == [s["id"] for s in memoir["sections"]]
    assert found["documents"] == [] and found["fill"] is None


def test_model_drawer_wins_over_keywords(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    writer.to_complete = [{"text": "nombre d'agents affectés au site", "kind": "tender"}]
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)
    found = item(c, bid, KEY)
    assert found is not None and found["kind"] == "tender"


def test_answer_replaces_everywhere_and_records_an_edit(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    writer.matrix = quote_everything
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    assert memoir["conformity_status"] == "ready"
    res = c.post(f"/bids/{bid}/missing/answer", json={"key": KEY, "answer": "  4 agents  "})
    assert res.status_code == 200, res.text
    assert all(i["key"] != KEY for i in res.json()["items"])
    after = latest(c, memoir["id"])
    for section in after["sections"]:
        assert MARK not in section["content_md"] and "4 agents" in section["content_md"]
        assert section["edited_by_user"] is True
        revisions = c.get(f"/memoir-sections/{section['id']}/revisions").json()
        assert revisions[0]["origin"] == "edited"
    assert after["conformity_status"] == "stale"


def test_answer_after_a_manual_edit_changes_nothing(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    section = memoir["sections"][0]
    body = section["content_md"].replace(MARK, "[À COMPLÉTER : nom du chef d'équipe]")
    edited = c.put(
        f"/memoir-sections/{section['id']}",
        json={"body_md": body, "base_revision": section["revision"]},
    )
    assert edited.status_code == 200, edited.text
    key = marker_key("nom du chef d'équipe")
    assert item(c, bid, key) is not None
    # the chapter changes again before the answer arrives: the marker is gone
    current = next(s for s in latest(c, memoir["id"])["sections"] if s["id"] == section["id"])
    c.put(
        f"/memoir-sections/{section['id']}",
        json={
            "body_md": current["content_md"].replace(
                "[À COMPLÉTER : nom du chef d'équipe]", "M. X"
            ),
            "base_revision": current["revision"],
        },
    )
    before = next(s for s in latest(c, memoir["id"])["sections"] if s["id"] == section["id"])
    res = c.post(f"/bids/{bid}/missing/answer", json={"key": key, "answer": "Mme Y"})
    assert res.status_code == 200
    after = next(s for s in latest(c, memoir["id"])["sections"] if s["id"] == section["id"])
    assert after["revision"] == before["revision"] and after["content_md"] == before["content_md"]


def test_empty_or_long_answer_is_refused(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    assert (
        c.post(f"/bids/{bid}/missing/answer", json={"key": KEY, "answer": "   "}).status_code == 422
    )
    long = "x" * 2001
    assert (
        c.post(f"/bids/{bid}/missing/answer", json={"key": KEY, "answer": long}).status_code == 422
    )
    assert [s["revision"] for s in latest(c, memoir["id"])["sections"]] == [
        s["revision"] for s in memoir["sections"]
    ]


def test_remove_drops_the_sentence(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    writer.sentence = ". Ils sont formés."  # the marker is a sentence of its own
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    res = c.post(f"/bids/{bid}/missing/remove", json={"key": KEY})
    assert res.status_code == 200, res.text
    for old, new in zip(memoir["sections"], latest(c, memoir["id"])["sections"], strict=True):
        assert MARK not in new["content_md"]
        assert new["content_md"] == old["content_md"].replace(MARK + ". ", "")
        assert "Ils sont formés." in new["content_md"]


def test_busy_memoir_refuses_answer_and_remove(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, memoir = drafted_bid(c, queue)
    db.execute(
        update(MemoirSection)
        .where(MemoirSection.id == memoir["sections"][0]["id"])
        .values(status="generating")
    )
    db.commit()
    assert missing(c, bid)["memoir_busy"] is True
    for path, body in (("answer", {"key": KEY, "answer": "4"}), ("remove", {"key": KEY})):
        res = c.post(f"/bids/{bid}/missing/{path}", json=body)
        assert res.status_code == 409 and res.json()["error"]["code"] == "memoir_busy"


def test_other_company_bid_is_not_found(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    a = signed_in_client(make_client, outbox, 1)
    bid, _ = drafted_bid(a, queue)
    b = signed_in_client(make_client, outbox, 2)
    assert b.get(f"/bids/{bid}/missing").status_code == 404
    res = b.post(f"/bids/{bid}/missing/answer", json={"key": KEY, "answer": "4"})
    assert res.status_code == 404


def test_profile_gaps_and_no_memoir(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    bid = c.post("/bids", json={"title": "Nettoyage du gymnase"}).json()["id"]
    out = missing(c, bid)
    assert out["memoir_id"] is None and out["items"] == []
    assert out["profile_gaps"] == {"staff": True, "equipment": True, "references": True}
    added = c.post("/profile/equipment", json={"name": "Autolaveuse", "quantity": 2})
    assert added.status_code == 201, added.text
    assert missing(c, bid)["profile_gaps"]["equipment"] is False


def test_dc_items_join_the_list(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    bid = c.post("/bids", json={"title": "Nettoyage du gymnase"}).json()["id"]
    assert c.post(f"/bids/{bid}/documents/dc1").status_code == 201
    items = {i["text"]: i for i in missing(c, bid)["items"]}
    phone = items["téléphone (Profil > Identité)"]
    assert phone["kind"] == "identity" and phone["documents"] == ["dc1"]
    assert phone["sections"] == []
    # what the profile cannot give (the buyer's name, the signature) stays in the Documents tab
    assert "nom de l'acheteur" not in items and "lieu et date de signature" not in items
    company = c.get("/profile/company").json()
    company["phone"] = "04 77 00 00 00"
    assert c.put("/profile/company", json=company).status_code == 200
    res = c.post(f"/bids/{bid}/missing/regenerate-documents")
    assert res.status_code == 200, res.text
    assert "téléphone (Profil > Identité)" not in {i["text"] for i in res.json()["items"]}


def test_progress_counts_missing_items(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, writer: WriterModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid, _ = drafted_bid(c, queue)
    count = len(missing(c, bid)["items"])
    assert count >= 1
    assert c.get(f"/bids/{bid}").json()["progress"]["missing_count"] == count
