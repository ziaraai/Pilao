"""Chapter editing, history and memoir versions (US-4.4, P2-05)."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Connection, update

from app.db.models import MemoirSection
from tests.api.helpers import signed_in_client
from tests.api.test_memoir_drafting import (  # noqa: F401 - the model fixture
    Factory,
    Sections,
    WriterModel,
    drafted,
    latest,
    model,
    prepared,
    quote_everything,
    section,
)
from tests.conftest import FakeQueue, Outbox, _new_session

BODY = (
    "Nous affectons 12 agents au site.\n\n"
    "Nous entretenons 4321 m² de vitrerie.\n\n"
    "[À COMPLÉTER : nom du chef d'équipe]"
)


def edit(c: TestClient, section_id: str, body: str, base: int) -> Any:
    return c.put(f"/memoir-sections/{section_id}", json={"body_md": body, "base_revision": base})


def test_the_user_edits_a_chapter_and_every_version_is_kept(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel  # noqa: F811
) -> None:
    model.matrix = quote_everything
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    first = section(m, "1. Moyens")
    generated = first["content_md"]
    assert first["revision"] == 1 and m["conformity_status"] == "ready"
    history = c.get(f"/memoir-sections/{first['id']}/revisions").json()
    assert [(r["revision"], r["origin"], r["author"], r["model"]) for r in history] == [
        (1, "generated", None, "test/generation")
    ]

    res = edit(c, first["id"], f"## Titre changé\n\n{BODY}", 1)
    assert res.status_code == 200, res.text
    edited = section(res.json(), "1. Moyens")
    # The planned title is kept, the user's text replaces the chapter.
    assert edited["content_md"] == f"## 1. Moyens\n\n{BODY}"
    assert edited["revision"] == 2 and edited["edited_by_user"] is True
    assert [(f["type"], f.get("term")) for f in edited["flags"]] == [
        ("to_complete", None),
        ("number", "4321"),  # invented by the model and still there; 12 was typed by the user
    ]
    assert res.json()["conformity_status"] == "stale"  # the matrix predates the edit

    stale = edit(c, first["id"], "Autre texte", 1)  # started from revision 1, now 2
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "edit_conflict"

    history = c.get(f"/memoir-sections/{first['id']}/revisions").json()
    assert [(r["revision"], r["origin"]) for r in history] == [(2, "edited"), (1, "generated")]
    assert history[0]["author"] == "User 1" and history[0]["words"] == 14
    restored = c.post(
        f"/memoir-sections/{first['id']}/revisions/{history[1]['id']}/restore",
        json={"base_revision": 2},
    ).json()
    back = section(restored, "1. Moyens")
    assert back["content_md"] == generated and back["revision"] == 3
    assert back["edited_by_user"] is False
    assert [r["origin"] for r in c.get(f"/memoir-sections/{first['id']}/revisions").json()] == [
        "restored",
        "edited",
        "generated",
    ]

    assert c.post(f"/memoirs/{m['id']}/conformity").status_code == 202
    queue.drain_memoir()
    assert latest(c, m["id"])["conformity_status"] == "ready"


def test_a_regeneration_is_a_new_revision_with_its_instruction(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel  # noqa: F811
) -> None:
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    first = section(m, "1. Moyens")
    edit(c, first["id"], BODY, 1)
    c.post(f"/memoir-sections/{first['id']}/regenerate", json={"instruction": "Plus concis."})
    queue.drain_memoir()
    history = c.get(f"/memoir-sections/{first['id']}/revisions").json()
    assert [(r["revision"], r["origin"], r["instruction"]) for r in history] == [
        (3, "generated", "Plus concis."),
        (2, "edited", None),
        (1, "generated", None),
    ]
    assert section(latest(c, m["id"]), "1. Moyens")["edited_by_user"] is False


def test_editing_needs_a_drafted_idle_chapter_and_some_text(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel  # noqa: F811
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    first = section(m, "1. Moyens")["id"]
    assert edit(c, first, BODY, 0).json()["error"]["code"] == "memoir_not_generated"
    c.post(f"/memoirs/{m['id']}/generate")
    assert edit(c, first, BODY, 0).json()["error"]["code"] == "section_busy"
    queue.drain_memoir()
    assert edit(c, first, "  \n ", 1).json()["error"]["code"] == "empty_chapter"
    assert edit(c, first, "x" * 60_001, 1).status_code == 422
    unknown = c.post(
        f"/memoir-sections/{first}/revisions/{uuid.uuid4()}/restore", json={"base_revision": 1}
    )
    assert unknown.status_code == 404


def test_a_chapter_in_error_can_be_written_by_hand(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel  # noqa: F811
) -> None:
    model.broken = {"1. Moyens"}
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    first = section(m, "1. Moyens")
    assert first["status"] == "error" and first["revision"] == 0
    written = section(edit(c, first["id"], BODY, 0).json(), "1. Moyens")
    assert written["status"] == "ready" and written["error"] is None and written["revision"] == 1


def test_an_edit_during_the_matrix_makes_its_result_stale(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
    conn: Connection,
) -> None:
    def edited_meanwhile(sections: Sections, refs: list[str]) -> list[dict[str, Any]]:
        with _new_session(conn) as other:  # a colleague saves a chapter during the check
            other.execute(update(MemoirSection).values(revision=MemoirSection.revision + 1))
            other.commit()
        return quote_everything(sections, refs)

    model.matrix = edited_meanwhile
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    assert m["conformity_status"] == "stale"
    assert c.get(f"/memoirs/{m['id']}/conformity").json()["counts"]["covered"] == 2


def test_every_version_of_the_memoir_is_listed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel  # noqa: F811
) -> None:
    c = signed_in_client(make_client, outbox)
    v1 = drafted(c, queue)
    bid = c.get("/bids").json()[0]["id"]
    v2 = c.post(f"/bids/{bid}/memoir").json()
    versions = c.get(f"/bids/{bid}/memoirs").json()
    assert [
        (v["id"], v["version"], v["status"], v["chapters"], v["drafted"]) for v in versions
    ] == [
        (v2["id"], 2, "draft", 2, 0),
        (v1["id"], 1, "ready", 2, 2),
    ]
    assert latest(c, v1["id"])["version"] == 1  # an older version stays readable


def test_tenancy_isolation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: WriterModel  # noqa: F811
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    m = drafted(b, queue)
    sid = m["sections"][0]["id"]
    rev = b.get(f"/memoir-sections/{sid}/revisions").json()[0]["id"]
    assert edit(a, sid, BODY, 1).status_code == 404
    assert a.get(f"/memoir-sections/{sid}/revisions").status_code == 404
    assert (
        a.post(
            f"/memoir-sections/{sid}/revisions/{rev}/restore", json={"base_revision": 1}
        ).status_code
        == 404
    )
    bid = b.get("/bids").json()[0]["id"]
    assert a.get(f"/bids/{bid}/memoirs").status_code == 404
    # A revision of another chapter cannot be restored here.
    other = m["sections"][1]["id"]
    assert (
        b.post(
            f"/memoir-sections/{other}/revisions/{rev}/restore", json={"base_revision": 1}
        ).status_code
        == 404
    )


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    some = uuid.uuid4()
    assert anon.put(f"/memoir-sections/{some}", json={}).status_code == 401
    assert anon.get(f"/memoir-sections/{some}/revisions").status_code == 401
    assert anon.get(f"/bids/{some}/memoirs").status_code == 401
