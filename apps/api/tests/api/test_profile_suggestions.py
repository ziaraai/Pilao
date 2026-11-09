"""Pre-filling the profile from the company's documents (US-1.6): reading, proposals."""

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
from app.db.models import AiCall, AuditLog, Job, Organization, ProfileSuggestion
from tests.api.helpers import signed_in_client
from tests.api.test_knowledge import ready_doc
from tests.conftest import FakeQueue, Outbox
from tests.documents_helpers import make_pdf

Factory = Callable[[], TestClient]

# The useful lines of ENG PRO's 2017 memoir.
MEMOIR = make_pdf(
    [
        [
            "3 - MOYENS EN MATERIEL",
            "6 auto laveuses marque TENANTE 5400",
            "14 Mono-brosses de marque NILFISK",
        ],
        ["ORGANIGRAMME", "AGENTS DE SERVICES", "Nos clients : MERCIALYS"],
    ]
)
MONOBROSSE = {
    "name": "Mono-brosses Nilfisk",
    "category": "Monobrosses",
    "quantity": 14,
    "excerpt": "14 Mono-brosses de marque NILFISK",
}
ANSWER: dict[str, Any] = {
    "equipment": [
        {
            "name": "Auto laveuse Tenante 5400",
            "category": "Autolaveuses",
            "quantity": 6,
            "excerpt": "6 auto laveuses marque TENANTE 5400",
        },
        MONOBROSSE,
        MONOBROSSE,  # the model repeats itself
        {"name": "Autolaveuse Karcher", "quantity": 12, "excerpt": "12 autolaveuses Karcher"},
    ],
    "human_resources": [
        {"qualification": "Agent de service", "count": 25, "excerpt": "AGENTS DE SERVICES"}
    ],
    "references": [{"client_name": "MERCIALYS", "excerpt": "Nos clients : MERCIALYS"}],
}


class FakeModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        user = messages[-1]["content"]
        assert "<profile_document" in user
        self.prompts.append(user)
        return json.dumps(ANSWER), 800, 300, 0.01


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    fake = FakeModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def read(c: TestClient, queue: FakeQueue) -> dict[str, Any]:
    res = c.post("/profile/suggestions/read")
    assert res.status_code == 202, res.text
    queue.drain_profile_prefill()
    body: dict[str, Any] = c.get("/profile/suggestions").json()
    return body


def by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    names = ("qualification", "name", "client_name")
    return {next(i["data"][n] for n in names if i["data"].get(n)): i for i in body["items"]}


def test_reading_proposes_sourced_lines(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR, "memoire_2017.pdf")
    body = read(c, queue)
    assert body["job"]["status"] == "done" and body["job"]["progress"] == 100
    assert body["job"]["notes"] == [] and body["job"]["error"] is None
    assert body["documents_ready"] == 1
    items = by_name(body)
    assert set(items) == {
        "Agent de service",
        "Auto laveuse Tenante 5400",
        "Mono-brosses Nilfisk",
        "MERCIALYS",
    }
    laveuse = items["Auto laveuse Tenante 5400"]
    assert laveuse["kind"] == "equipment" and laveuse["missing"] == []
    assert laveuse["data"]["quantity"] == 6 and laveuse["page"] == 1
    assert laveuse["excerpt"] == "6 auto laveuses marque TENANTE 5400"
    assert laveuse["document_title"]
    assert items["Agent de service"]["missing"] == ["count"]  # 25 is not written
    assert items["MERCIALYS"]["missing"] == ["client_type", "title"]
    assert [i["kind"] for i in body["items"]] == [
        "human_resource",
        "equipment",
        "equipment",
        "reference",
    ]
    assert "6 auto laveuses" in model.prompts[0]
    calls = db.scalars(select(AiCall).where(AiCall.task == "profile_extraction")).all()
    assert len(calls) == 1


def test_what_the_profile_already_has_is_not_proposed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.post("/profile/equipment", json={"name": "Mono brosse nilfisk"}).status_code == 201
    ready_doc(c, queue, MEMOIR)
    assert "Mono-brosses Nilfisk" not in by_name(read(c, queue))


def test_reading_again_replaces_pending_only(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    first = by_name(read(c, queue))
    db.execute(
        update(ProfileSuggestion)
        .where(ProfileSuggestion.id == first["MERCIALYS"]["id"])
        .values(status="dismissed")
    )
    db.commit()
    again = read(c, queue)
    assert "MERCIALYS" not in by_name(again)  # dismissed: not proposed again
    assert len(again["items"]) == 3
    assert {i["id"] for i in again["items"]}.isdisjoint({i["id"] for i in first.values()})
    total = db.scalars(select(ProfileSuggestion)).all()
    assert len(total) == 4  # 3 new pending + the dismissed one


def test_reading_needs_a_document_and_runs_once(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    res = c.post("/profile/suggestions/read")
    assert res.status_code == 409 and res.json()["error"]["code"] == "no_documents"
    ready_doc(c, queue, MEMOIR)
    org = db.scalars(select(Organization)).one()
    job = Job(
        kind="profile_prefill",
        ref_id=org.id,
        org_id=org.id,
        status="running",
        created_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db.add(job)
    db.commit()
    res = c.post("/profile/suggestions/read")
    assert res.status_code == 409 and res.json()["error"]["code"] == "already_running"
    job.created_at = datetime.now(UTC) - timedelta(minutes=40)  # stuck: no longer blocks
    db.commit()
    assert c.post("/profile/suggestions/read").status_code == 202


def test_a_document_that_gives_nothing_is_named_in_the_notes(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    policy = "Ce document presente notre demarche qualite et nos engagements environnementaux."
    empty_id = ready_doc(c, queue, make_pdf([[policy]]), "vide.pdf")
    title = c.get(f"/knowledge/{empty_id}").json()["title"]
    body = read(c, queue)
    assert body["job"]["status"] == "done"
    assert body["job"]["notes"] == [f"{title} : aucun passage sur vos moyens ou vos références."]
    assert "Auto laveuse Tenante 5400" in by_name(body)  # the other document still counts
    assert len(model.prompts) == 2


def test_no_model_configured_is_reported(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "")
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    body = read(c, queue)
    assert body["job"]["status"] == "error"
    assert body["job"]["error"] == "Aucun modèle configuré pour la tâche « profile_extraction »."
    assert body["items"] == [] and model.prompts == []


def test_another_company_sees_nothing(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    a = signed_in_client(make_client, outbox)
    ready_doc(a, queue, MEMOIR)
    assert len(read(a, queue)["items"]) == 4
    b = signed_in_client(make_client, outbox, n=2)
    body = b.get("/profile/suggestions").json()
    assert body == {"job": None, "documents_ready": 0, "items": []}


def accept(c: TestClient, *items: tuple[dict[str, Any], dict[str, Any]]) -> dict[str, Any]:
    res = c.post(
        "/profile/suggestions/accept",
        json={"items": [{"id": s["id"], "data": {**s["data"], **edit}} for s, edit in items]},
    )
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def test_accepting_adds_to_the_profile(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    items = by_name(read(c, queue))
    before = c.get("/profile/completeness").json()["pct"]
    mercialys = {"client_type": "private", "title": "Nettoyage de la galerie", "year": 2016}
    result = accept(c, (items["Auto laveuse Tenante 5400"], {}), (items["MERCIALYS"], mercialys))
    assert result == {"created": 2, "errors": []}
    equipment = c.get("/profile/equipment").json()
    assert [(e["name"], e["quantity"]) for e in equipment] == [("Auto laveuse Tenante 5400", 6)]
    [ref] = c.get("/profile/references").json()
    assert (ref["client_name"], ref["title"], ref["year"]) == (
        "MERCIALYS",
        "Nettoyage de la galerie",
        2016,
    )
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "create")).all()
    assert {log.entity for log in logs} >= {"equipment", "company_references"}
    assert all("from_suggestion" in log.meta for log in logs if log.entity == "equipment")
    assert c.get("/profile/completeness").json()["pct"] > before
    left = by_name(c.get("/profile/suggestions").json())
    assert set(left) == {"Agent de service", "Mono-brosses Nilfisk"}


def test_an_incomplete_line_is_refused_and_the_others_pass(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    items = by_name(read(c, queue))
    agent = items["Agent de service"]
    result = accept(c, (agent, {}), (items["Mono-brosses Nilfisk"], {}))
    assert result["created"] == 1
    assert result["errors"] == [{"id": agent["id"], "message": "À compléter : Nombre"}]
    assert "Agent de service" in by_name(c.get("/profile/suggestions").json())  # still pending
    assert accept(c, (agent, {"count": 8}))["created"] == 1
    [hr] = c.get("/profile/human-resources").json()
    assert (hr["qualification"], hr["count"]) == ("Agent de service", 8)


def test_accepting_twice_creates_one_line(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    laveuse = by_name(read(c, queue))["Auto laveuse Tenante 5400"]
    assert accept(c, (laveuse, {}))["created"] == 1
    again = accept(c, (laveuse, {}))
    assert again == {
        "created": 0,
        "errors": [{"id": laveuse["id"], "message": "Proposition introuvable ou déjà traitée."}],
    }
    assert len(c.get("/profile/equipment").json()) == 1


def test_dismiss(make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel) -> None:
    a = signed_in_client(make_client, outbox)
    ready_doc(a, queue, MEMOIR)
    mercialys = by_name(read(a, queue))["MERCIALYS"]
    b = signed_in_client(make_client, outbox, n=2)
    assert b.post(f"/profile/suggestions/{mercialys['id']}/dismiss").status_code == 404
    other = accept(b, (mercialys, {"client_type": "private", "title": "Galerie"}))
    assert other["created"] == 0 and b.get("/profile/references").json() == []
    assert a.post(f"/profile/suggestions/{mercialys['id']}/dismiss").status_code == 204
    assert a.post(f"/profile/suggestions/{mercialys['id']}/dismiss").status_code == 404
    assert "MERCIALYS" not in by_name(a.get("/profile/suggestions").json())
    assert "MERCIALYS" not in by_name(read(a, queue))  # not proposed again


def test_reading_again_after_adding_everything_has_no_misleading_note(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    for s in read(c, queue)["items"]:
        assert c.post(f"/profile/suggestions/{s['id']}/dismiss").status_code == 204
    again = read(c, queue)
    assert again["items"] == []
    assert again["job"]["notes"] == []  # the document has lines: all already decided


def test_an_unexpected_failure_ends_the_reading(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: FakeModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import profile_prefill

    def broken(*_: Any) -> None:
        raise RuntimeError("disk unplugged")

    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    monkeypatch.setattr(profile_prefill, "document_blocks", broken)
    assert c.post("/profile/suggestions/read").status_code == 202
    with pytest.raises(RuntimeError):
        queue.drain_profile_prefill()  # RQ logs it and may retry
    job = c.get("/profile/suggestions").json()["job"]
    assert job["status"] == "error"
    assert job["error"] == "La lecture s'est interrompue. Relancez-la."
    assert c.post("/profile/suggestions/read").status_code == 202  # not blocked


def test_a_stuck_reading_is_reported_and_can_be_restarted(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    ready_doc(c, queue, MEMOIR)
    org = db.scalars(select(Organization)).one()
    db.add(
        Job(
            kind="profile_prefill",
            ref_id=org.id,
            org_id=org.id,
            status="running",
            created_at=datetime.now(UTC) - timedelta(minutes=40),
        )
    )
    db.commit()
    job = c.get("/profile/suggestions").json()["job"]
    assert job["status"] == "error"  # the worker died: the screen must not wait forever
    assert job["error"] == "La lecture s'est interrompue. Relancez-la."
