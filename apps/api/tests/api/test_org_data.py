"""GDPR rights of an organization: full export and erasure (docs/09, ADR-026)."""

import io
import json
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import DataRequest, File, Organization, PurgeLog, Tender, User
from app.schemas.tenders import TenderIn
from app.services.alerts import run_daily
from app.services.org_data import EXCLUDED_TABLES
from app.services.tenders import ingest
from tests.api.helpers import PASSWORD, signed_in_client
from tests.api.test_vault import confirm, deposit
from tests.conftest import FakeQueue, MemoryStorage, Outbox
from tests.documents_helpers import make_docx

Factory = Callable[[], TestClient]
NOW = datetime.now(UTC)
ORG_TABLES = [t for t in Base.metadata.sorted_tables if "org_id" in t.c and t.name != "purge_logs"]


def populate(c: TestClient, queue: FakeQueue, marker: str) -> None:
    """A company with a bit of everything, its texts marked to spot leaks."""
    assert c.put("/profile", json={"keywords_include": [f"mot{marker}"]}).status_code == 200
    c.post("/profile/human-resources", json={"qualification": f"Agent {marker}", "count": 3})
    c.post(
        "/profile/references",
        json={"client_name": f"Client {marker}", "client_type": "public", "title": f"Réf {marker}"},
    )
    confirm(c, deposit(c, name=f"urssaf-{marker}.pdf").json()["id"])
    doc = make_docx([("Normal", f"Méthode secrète {marker}.")])
    c.post(
        "/knowledge",
        data={"kind": "past_memoir"},
        files={"file": (f"m-{marker}.docx", doc, "application/octet-stream")},
    )
    queue.drain()
    c.post("/bids", json={"title": f"Dossier {marker}"})


def export_zip(
    c: TestClient, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> zipfile.ZipFile:
    res = c.post("/organization/exports")
    assert res.status_code == 202 and res.json()["status"] == "pending"
    queue.drain_org_exports()
    [latest, *_] = c.get("/organization/data-requests").json()
    assert latest["status"] == "ready" and latest["filename"].endswith(".zip")
    key = db.get_one(File, uuid.UUID(latest["file_id"])).storage_key
    return zipfile.ZipFile(io.BytesIO(storage.objects[key]))


def org_id_of(db: Session, name: str) -> uuid.UUID:
    return db.scalar(select(Organization.id).where(Organization.name == name))  # type: ignore[return-value]


def test_the_export_holds_every_table_of_the_company_and_nothing_else(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    populate(a, queue, "AAA")
    populate(b, queue, "BBB")
    archive = export_zip(a, queue, storage, db)
    names = archive.namelist()
    assert names[:2] == ["LISEZ-MOI.txt", "donnees.json"]
    raw = archive.read("donnees.json").decode("utf-8")
    data: dict[str, list[dict[str, Any]]] = json.loads(raw)
    org_a = str(org_id_of(db, "Entreprise 1"))

    expected = {t.name for t in ORG_TABLES if t.name not in EXCLUDED_TABLES}
    assert expected | {"organizations", "tenders"} == set(data)
    assert all(row["org_id"] == org_a for t in expected for row in data[t])
    assert data["organizations"][0]["id"] == org_a
    assert [h["qualification"] for h in data["human_resources"]] == ["Agent AAA"]
    assert data["bids"][0]["title"] == "Dossier AAA" and data["audit_logs"]
    assert "BBB" not in raw and "user2@example.fr" not in raw  # never another company's data
    columns = {key for rows in data.values() for row in rows for key in row}
    assert not columns & {"password_hash", "token_hash", "embedding", "embedding_text_hash"}
    assert "user1@example.fr" in raw  # the company's own accounts are part of its data
    files = [n for n in names if n.startswith("fichiers/")]
    a_files = db.scalars(select(File).where(File.org_id == uuid.UUID(org_a))).all()
    originals = {f.id: f for f in a_files if f.filename.endswith((".pdf", ".docx"))}
    assert len(files) == len(originals) == 2  # the attestation and the knowledge document
    for record in originals.values():
        [name] = [n for n in files if n.startswith(f"fichiers/{record.id}-")]
        assert archive.read(name) == storage.objects[record.storage_key]

    first_key = {
        f.storage_key for f in db.scalars(select(File).where(File.mime == "application/zip"))
    }
    second = export_zip(a, queue, storage, db)
    assert not any(n.endswith(".zip") for n in second.namelist())  # no export inside an export
    zips = db.scalars(select(File).where(File.mime == "application/zip")).all()
    assert len(zips) == 1 and zips[0].storage_key not in first_key  # only the latest is kept
    assert not first_key & set(storage.objects)


def test_only_an_administrator_exports_or_deletes(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    db.execute(update(User).values(role="org_member"))
    db.commit()
    assert c.post("/organization/exports").status_code == 403
    assert (
        c.post("/organization/deletion", json={"confirmation": "Entreprise 1"}).status_code == 403
    )
    assert c.get("/organization/data-requests").status_code == 403
    assert c.get("/organization/deletion").json() == {"due_at": None, "requested_at": None}


def test_deletion_is_scheduled_cancellable_then_erases_everything(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    populate(a, queue, "AAA")
    populate(b, queue, "BBB")
    ingest(db, [TenderIn(source="boamp", source_id="PUB-1", title="Annonce publique")], outbox)
    org_a, org_b = org_id_of(db, "Entreprise 1"), org_id_of(db, "Entreprise 2")

    wrong = a.post("/organization/deletion", json={"confirmation": "Entreprise 2"})
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "confirmation_mismatch"
    sent = len(outbox.sent)
    scheduled = a.post("/organization/deletion", json={"confirmation": "  entreprise 1 "})
    assert scheduled.status_code == 202
    due = datetime.fromisoformat(scheduled.json()["due_at"])
    assert timedelta(days=29, hours=23) < due - NOW <= timedelta(days=30, minutes=5)
    [mail] = outbox.sent[sent:]
    assert mail.to == "user1@example.fr" and "programmée le" in mail.subject
    assert (
        a.post("/organization/deletion", json={"confirmation": "Entreprise 1"}).status_code == 409
    )
    assert a.get("/organization/deletion").json()["due_at"] == scheduled.json()["due_at"]
    assert b.get("/organization/deletion").json()["due_at"] is None  # the other company

    assert a.delete("/organization/deletion").status_code == 204
    assert a.get("/organization/deletion").json()["due_at"] is None
    assert outbox.sent[-1].subject == "Suppression des données de Entreprise 1 annulée"
    assert (
        a.post("/organization/deletion", json={"confirmation": "Entreprise 1"}).status_code == 202
    )

    a_keys = set(db.scalars(select(File.storage_key).where(File.org_id == org_a)))
    b_keys = set(db.scalars(select(File.storage_key).where(File.org_id == org_b)))
    assert a_keys and b_keys
    assert (
        run_daily(db, outbox, NOW + timedelta(days=29), storage=storage).organizations_erased == 0
    )
    report = run_daily(db, outbox, NOW + timedelta(days=31), storage=storage)
    assert report.organizations_erased == 1

    for table in ORG_TABLES:  # every table, vector index included
        assert (
            db.scalar(select(func.count()).select_from(table).where(table.c.org_id == org_a)) == 0
        )
        if table.name in ("users", "human_resources", "document_chunks", "files"):
            assert db.scalar(select(func.count()).select_from(table).where(table.c.org_id == org_b))
    assert db.get(Organization, org_a) is None
    assert not a_keys & set(storage.objects) and b_keys <= set(storage.objects)
    assert db.scalar(select(func.count()).select_from(Tender)) == 1  # public data stays
    [receipt] = db.scalars(select(PurgeLog)).all()
    assert receipt.org_id == org_a and receipt.objects == len(a_keys)
    assert receipt.rows["users"] == 1 and receipt.rows["document_chunks"] >= 1
    assert outbox.sent[-1].subject == "Les données de Entreprise 1 ont été supprimées"
    assert a.get("/auth/me").status_code == 401  # sessions went with the account
    # the other company is intact (31 days later its session has expired: it logs in again)
    login = {"email": "user2@example.fr", "password": PASSWORD}
    assert b.post("/auth/login", json=login).status_code == 200


def test_a_storage_failure_keeps_everything_for_the_next_run(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    storage: MemoryStorage,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = signed_in_client(make_client, outbox)
    populate(c, queue, "AAA")
    c.post("/organization/deletion", json={"confirmation": "Entreprise 1"})
    org = org_id_of(db, "Entreprise 1")

    def down(key: str) -> None:
        raise RuntimeError("storage down")

    monkeypatch.setattr(storage, "delete", down)
    assert (
        run_daily(db, outbox, NOW + timedelta(days=31), storage=storage).organizations_erased == 0
    )
    assert db.get(Organization, org) is not None
    error = db.scalar(select(DataRequest.error).where(DataRequest.kind == "deletion"))
    assert error == "Suppression des fichiers interrompue : nouvelle tentative dans une heure."
    monkeypatch.undo()
    assert (
        run_daily(db, outbox, NOW + timedelta(days=31), storage=storage).organizations_erased == 1
    )
    assert db.get(Organization, org) is None


def test_an_unavailable_queue_is_reported(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    queue.down = True
    res = c.post("/organization/exports").json()
    assert (
        res["status"] == "error"
        and res["error"] == "File d'attente indisponible : relancez l'export."
    )


def test_tenancy_and_authentication(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    export_zip(a, queue, storage, db)
    [req] = a.get("/organization/data-requests").json()
    assert b.get("/organization/data-requests").json() == []
    assert b.get(f"/files/{req['file_id']}/download-url").status_code == 404
    anon = make_client()
    assert anon.post("/organization/exports").status_code == 401
    assert anon.get("/organization/deletion").status_code == 401
