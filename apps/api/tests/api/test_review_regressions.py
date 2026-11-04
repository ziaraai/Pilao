"""Regression tests for issues found during the full review (P1-01 to P1-07)."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument
from tests.api.helpers import signed_in_client
from tests.api.test_knowledge import PDF_MEMO, deposit, ready_doc
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]


def test_generic_file_delete_cannot_bypass_knowledge_index_cleanup(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)
    file_id = c.get(f"/knowledge/{doc_id}").json()["file_id"]
    res = c.delete(f"/files/{file_id}")
    assert res.status_code == 409 and res.json()["error"]["code"] == "file_in_use"
    assert db.scalars(select(DocumentChunk)).all()  # index untouched
    assert c.get(f"/knowledge/{doc_id}").status_code == 200


def test_vault_file_cannot_be_deleted_through_files_endpoint(
    make_client: Factory, outbox: Outbox
) -> None:
    from tests.api.test_vault import deposit as vault_deposit

    c = signed_in_client(make_client, outbox)
    file_id = vault_deposit(c).json()["file_id"]
    assert c.delete(f"/files/{file_id}").json()["error"]["code"] == "file_in_use"


def test_document_deleted_during_indexing_leaves_no_orphan_chunks(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    c = signed_in_client(make_client, outbox)
    doc_id = deposit(c, PDF_MEMO).json()["id"]

    from app.services import knowledge

    original = knowledge._embed_chunks

    def embed_then_user_deletes(*args, **kwargs):  # type: ignore[no-untyped-def]
        vectors = original(*args, **kwargs)
        assert c.delete(f"/knowledge/{doc_id}").status_code == 204  # user deletes meanwhile
        return vectors

    monkeypatch.setattr(knowledge, "_embed_chunks", embed_then_user_deletes)
    queue.drain()  # must not raise nor recreate chunks
    assert db.scalars(select(DocumentChunk)).all() == []
    assert db.scalars(select(KnowledgeDocument)).all() == []


def test_settings_default_to_production_rules(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import Settings

    monkeypatch.delenv("ENVIRONMENT", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.environment == "production" and s.cookie_secure


def test_cors_allows_only_the_web_app(make_client: Factory) -> None:
    c = make_client()
    preflight = {"Access-Control-Request-Method": "POST"}
    ok = c.options("/auth/login", headers={**preflight, "Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert ok.headers.get("access-control-allow-credentials") == "true"
    evil = c.options("/auth/login", headers={**preflight, "Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in evil.headers


def test_ai_budget_also_caps_embeddings(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from decimal import Decimal

    from app.core.config import get_settings
    from app.db.models import AiCall, Organization

    c = signed_in_client(make_client, outbox)
    org = db.scalars(select(Organization)).one()
    db.add(AiCall(org_id=org.id, task="x", model="m", cost_eur=Decimal(60)))
    db.commit()
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_eur_per_org", 50.0)

    doc_id = deposit(c, PDF_MEMO).json()["id"]
    queue.drain()  # permanent failure: no exception, no retry
    doc = c.get(f"/knowledge/{doc_id}").json()
    assert doc["status"] == "error" and "Budget" in doc["error"]
    res = c.get("/knowledge/search", params={"q": "autolaveuses"})
    assert res.status_code == 429 and res.json()["error"]["code"] == "ai_budget_exceeded"
