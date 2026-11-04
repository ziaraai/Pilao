import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import Memoir
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import DCE, FakeModel, full_answer, install_fake_model
from tests.api.test_bids import deposit, new_bid
from tests.conftest import CountingEmbedder, FakeQueue, Outbox
from tests.documents_helpers import make_docx

Factory = Callable[[], TestClient]


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    return install_fake_model(monkeypatch)


def analyzed_bid(c: TestClient, queue: FakeQueue) -> str:
    bid = new_bid(c)
    deposit(c, bid, DCE)
    queue.drain_dce()
    queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "ready"
    return bid


def add_reference(c: TestClient, **kw: Any) -> str:
    body = {"client_name": "Client", "client_type": "private", "title": "Divers", **kw}
    res = c.post("/profile/references", json=body)
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def test_memoir_needs_a_ready_analysis(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    assert c.post(f"/bids/{bid}/memoir").json()["error"]["code"] == "no_analysis"
    assert c.get(f"/bids/{bid}/memoir").status_code == 404


def test_imposed_outline_is_used_word_for_word(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = analyzed_bid(c, queue)
    m = c.post(f"/bids/{bid}/memoir").json()
    assert m["outline_source"] == "rc_imposed" and m["status"] == "draft" and m["version"] == 1
    assert [s["title"] for s in m["sections"]] == ["1. Moyens", "2. Méthodologie"]
    where = {ref: s["title"] for s in m["sections"] for ref in s["requirement_refs"]}
    assert where == {"CCTP-1": "2. Méthodologie", "CCTP-2": "2. Méthodologie"}
    assert m["unassigned_requirements"] == [] and m["word_budget"] == 12 * 500 * 9 // 10
    assert all(s["word_budget"] >= 150 and s["status"] == "pending" for s in m["sections"])


def test_sector_outline_when_the_rc_imposes_none(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    model.extra = {
        "memoir_requirements": {
            "imposed_outline": [],
            "max_pages": 8,
            "source": {"file": "DCE/RC.pdf", "page": 2},
        }
    }
    c = signed_in_client(make_client, outbox)
    m = c.post(f"/bids/{analyzed_bid(c, queue)}/memoir").json()
    assert m["outline_source"] == "sector_default" and len(m["sections"]) == 9
    assert m["max_pages"] == 8 and m["word_budget"] == 8 * 450


def test_company_template_outline_ordered_by_criteria(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    model.extra = {
        "memoir_requirements": {"imposed_outline": [], "max_pages": None, "source": None},
        "award_criteria": [
            {
                "name": "Valeur technique",
                "weight_pct": 60,
                "source": {"file": "DCE/RC.pdf", "page": 2},
                "subcriteria": [
                    {"name": "Méthodologie", "weight_pct": 35},
                    {"name": "Moyens humains", "weight_pct": 25},
                ],
            }
        ],
    }
    c = signed_in_client(make_client, outbox)
    template = make_docx(
        [
            ("Heading 1", "1. Présentation de la société"),
            ("Normal", "Texte."),
            ("Heading 1", "2. Moyens humains"),
            ("Normal", "Texte."),
            ("Heading 1", "3. Méthodologie"),
            ("Normal", "Texte."),
        ]
    )
    res = c.post(
        "/knowledge",
        data={"kind": "memoir_template"},
        files={"file": ("modele.docx", template, "application/octet-stream")},
    )
    assert res.status_code == 201
    queue.drain()
    m = c.post(f"/bids/{analyzed_bid(c, queue)}/memoir").json()
    assert m["outline_source"] == "org_template"
    assert [s["title"] for s in m["sections"]] == [
        "3. Méthodologie",
        "2. Moyens humains",
        "1. Présentation de la société",
    ]
    assert [s["criterion_ref"] for s in m["sections"]] == ["Méthodologie", "Moyens humains", None]


def test_references_are_ranked_and_explained(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    key_info = full_answer()["key_info"]
    key_info["estimated_amount_eur_ht"] = {
        "value": 120000,
        "source": {"file": "DCE/RC.pdf", "page": 1},
    }
    model.extra = {"key_info": key_info}
    c = signed_in_client(make_client, outbox)
    close = add_reference(
        c,
        client_name="Mairie de Lyon",
        client_type="public",
        title="Nettoyage quotidien des bureaux de la mairie",
        year=2025,
        amount_cents=11_000_000,
    )
    for i in range(4):
        add_reference(c, title=f"Désinfection de navires {i}", year=2012, amount_cents=500_000)
    m = c.post(f"/bids/{analyzed_bid(c, queue)}/memoir").json()
    refs = m["references"]
    assert refs[0]["id"] == close and refs[0]["selected"]
    assert {"client public", "récente", "montant comparable"} <= set(refs[0]["reasons"])
    assert 3 <= sum(r["selected"] for r in refs) <= 5 and len(refs) == 5


def test_no_reference_is_never_invented(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.post(f"/bids/{analyzed_bid(c, queue)}/memoir").json()["references"] == []


def test_reference_embeddings_are_reused_until_the_reference_changes(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: FakeModel,
    embedder: CountingEmbedder,
) -> None:
    c = signed_in_client(make_client, outbox)
    ref = add_reference(c, title="Nettoyage de bureaux")
    bid = analyzed_bid(c, queue)
    c.post(f"/bids/{bid}/memoir")
    before = embedder.texts_embedded
    c.post(f"/bids/{bid}/memoir")
    assert embedder.texts_embedded == before + 1  # only the tender query, not the reference
    c.put(
        f"/profile/references/{ref}",
        json={"client_name": "Client", "client_type": "private", "title": "Vitrerie"},
    )
    c.post(f"/bids/{bid}/memoir")
    assert embedder.texts_embedded == before + 3  # query + the edited reference


def test_user_edits_the_outline_before_drafting(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    m = c.post(f"/bids/{analyzed_bid(c, queue)}/memoir").json()
    first, second = m["sections"]
    body = {
        "sections": [
            {
                "id": second["id"],
                "title": "Méthodologie détaillée",
                "requirement_refs": ["CCTP-1"],
                "word_budget": 800,
            },
            {
                "title": "Nouveau chapitre",
                "requirement_refs": ["CCTP-2", "CCTP-2"],
                "word_budget": 300,
            },
        ]
    }
    edited = c.put(f"/memoirs/{m['id']}/outline", json=body).json()
    assert [s["title"] for s in edited["sections"]] == [
        "Méthodologie détaillée",
        "Nouveau chapitre",
    ]
    assert edited["sections"][0]["id"] == second["id"] and first["id"] not in [
        s["id"] for s in edited["sections"]
    ]
    assert edited["sections"][1]["requirement_refs"] == ["CCTP-2"] and edited["word_budget"] == 1100
    assert edited["unassigned_requirements"] == []
    dropped = c.put(
        f"/memoirs/{m['id']}/outline",
        json={"sections": [{"title": "Seul", "requirement_refs": []}]},
    ).json()
    assert dropped["unassigned_requirements"] == ["CCTP-1", "CCTP-2"]  # shown to the user
    bad = c.put(
        f"/memoirs/{m['id']}/outline",
        json={"sections": [{"title": "X", "requirement_refs": ["CCTP-99"]}]},
    )
    assert bad.json()["error"]["code"] == "unknown_requirement"
    assert c.put(f"/memoirs/{m['id']}/outline", json={"sections": []}).status_code == 422
    db.execute(update(Memoir).values(status="generating"))
    db.commit()
    assert (
        c.put(f"/memoirs/{m['id']}/outline", json=body).json()["error"]["code"] == "memoir_locked"
    )


def test_user_chooses_the_references(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    a, b = add_reference(c, title="A"), add_reference(c, title="B")
    m = c.post(f"/bids/{analyzed_bid(c, queue)}/memoir").json()
    chosen = c.put(f"/memoirs/{m['id']}/references", json={"reference_ids": [b]}).json()
    assert [r["id"] for r in chosen["references"] if r["selected"]] == [b]
    assert (
        c.put(f"/memoirs/{m['id']}/references", json={"reference_ids": [str(uuid.uuid4())]}).json()[
            "error"
        ]["code"]
        == "unknown_reference"
    )
    assert a in [r["id"] for r in chosen["references"]]  # still proposed


def test_each_preparation_is_a_new_version(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = analyzed_bid(c, queue)
    c.post(f"/bids/{bid}/memoir")
    second = c.post(f"/bids/{bid}/memoir").json()
    assert second["version"] == 2 and c.get(f"/bids/{bid}/memoir").json()["id"] == second["id"]


def test_tenancy_isolation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    foreign_ref = add_reference(a, title="Référence de A")
    bid = analyzed_bid(b, queue)
    m = b.post(f"/bids/{bid}/memoir").json()
    assert all(r["id"] != foreign_ref for r in m["references"])  # never another company's data
    assert a.get(f"/bids/{bid}/memoir").status_code == 404
    assert a.post(f"/bids/{bid}/memoir").status_code == 404
    assert (
        a.put(f"/memoirs/{m['id']}/outline", json={"sections": [{"title": "x"}]}).status_code == 404
    )
    assert (
        b.put(f"/memoirs/{m['id']}/references", json={"reference_ids": [foreign_ref]}).json()[
            "error"
        ]["code"]
        == "unknown_reference"
    )


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.post(f"/bids/{uuid.uuid4()}/memoir").status_code == 401
    assert anon.get(f"/bids/{uuid.uuid4()}/memoir").status_code == 401
