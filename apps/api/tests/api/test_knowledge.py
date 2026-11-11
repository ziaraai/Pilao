import io
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import EmbeddingError
from app.db.models import AiCall, DocumentChunk, File, Job, KnowledgeDocument
from tests.api.helpers import signed_in_client
from tests.conftest import CountingEmbedder, FakeQueue, FakeScanner, MemoryStorage, Outbox
from tests.documents_helpers import make_blank_pdf, make_docx, make_pdf

Factory = Callable[[], TestClient]

PDF_MEMO = make_pdf(
    [
        ["1. Presentation de l'entreprise", "", "Entreprise de nettoyage de locaux creee en 2010."],
        [
            "2. Moyens materiels",
            "",
            "Nous utilisons des autolaveuses et des monobrosses professionnelles.",
        ],
        [
            "3. Hygiene et securite",
            "",
            "Les agents portent des equipements de protection individuelle.",
        ],
    ]
)


def deposit(
    c: TestClient, content: bytes, name: str = "memoire.pdf", kind: str = "past_memoir", **form: str
) -> Any:
    return c.post(
        "/knowledge",
        data={"kind": kind, **form},
        files={"file": (name, content, "application/octet-stream")},
    )


def ready_doc(
    c: TestClient, queue: FakeQueue, content: bytes = PDF_MEMO, name: str = "memoire.pdf"
) -> str:
    res = deposit(c, content, name)
    assert res.status_code == 201, res.text
    queue.drain()
    return str(res.json()["id"])


def test_upload_is_pending_then_indexed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    res = deposit(
        c, PDF_MEMO, "Mémoire 2023.pdf", title="Mon mémoire modèle", kind="memoir_template"
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "pending" and body["title"] == "Mon mémoire modèle"
    assert queue.pending and db.scalars(select(Job)).one().status == "pending"

    queue.drain()
    doc = c.get(f"/knowledge/{body['id']}").json()
    assert doc["status"] == "ready" and doc["error"] is None
    assert doc["page_count"] == 3 and doc["chunk_count"] >= 3  # one section per page
    job = db.scalars(select(Job)).one()
    assert job.status == "done" and job.started_at and job.finished_at

    chunks = db.scalars(select(DocumentChunk).order_by(DocumentChunk.position)).all()
    assert [c.heading for c in chunks][:3] == [
        "1. Presentation de l'entreprise",
        "2. Moyens materiels",
        "3. Hygiene et securite",
    ]
    assert [c.page_from for c in chunks][:3] == [1, 2, 3]
    assert all(len(c.embedding) == 1024 and c.source_type == "knowledge" for c in chunks)
    assert db.scalars(select(AiCall).where(AiCall.task == "embedding")).first().success is True  # type: ignore[union-attr]


def test_default_title_is_the_filename(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    assert deposit(c, PDF_MEMO, "qse.pdf", kind="qse_policy").json()["title"] == "qse.pdf"


def test_docx_is_supported(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    docx = make_docx(
        [("Heading 1", "Politique QSE"), ("Normal", "Nous sommes certifies ISO 9001.")]
    )
    doc_id = ready_doc(c, queue, docx, "qse.docx")
    assert c.get(f"/knowledge/{doc_id}").json()["status"] == "ready"


def test_search_returns_the_relevant_passage_with_its_source(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)
    hits = c.get("/knowledge/search", params={"q": "autolaveuses monobrosses", "k": 3}).json()
    assert hits and hits[0]["document_id"] == doc_id
    assert hits[0]["heading"] == "2. Moyens materiels" and hits[0]["page_from"] == 2
    assert "autolaveuses" in hits[0]["content"] and hits[0]["score"] > hits[-1]["score"] - 1e-9
    assert len(c.get("/knowledge/search", params={"q": "nettoyage", "k": 1}).json()) == 1


def test_search_never_returns_another_organizations_passages(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    secret = make_pdf(
        [["1. Prix confidentiels", "", "Notre taux horaire secret est de quarante euros."]]
    )
    ready_doc(b, queue, secret, "prix.pdf")
    ready_doc(a, queue)
    # Same words as B's secret: A must only get its own passages, B must get B's.
    mine = a.get("/knowledge/search", params={"q": "taux horaire secret prix", "k": 20}).json()
    assert mine and all("secret" not in h["content"] for h in mine)
    theirs = b.get("/knowledge/search", params={"q": "taux horaire secret prix", "k": 20}).json()
    assert len(theirs) == 1 and "secret" in theirs[0]["content"]


def test_search_ignores_documents_not_ready(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    deposit(c, PDF_MEMO)  # still pending: not drained
    assert c.get("/knowledge/search", params={"q": "autolaveuses"}).json() == []


def test_reindex_is_idempotent_and_reuses_embeddings(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, embedder: CountingEmbedder, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)
    first = {ch.content_hash for ch in db.scalars(select(DocumentChunk))}
    embedded_before = embedder.texts_embedded

    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 202
    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 409  # already queued
    queue.drain()

    chunks = db.scalars(select(DocumentChunk)).all()
    assert {ch.content_hash for ch in chunks} == first and len(chunks) == len(
        first
    )  # no duplicates
    assert embedder.texts_embedded == embedded_before  # same org, same text: cache hit
    assert c.get(f"/knowledge/{doc_id}").json()["status"] == "ready"


def test_same_text_in_another_org_is_re_embedded(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, embedder: CountingEmbedder
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    ready_doc(a, queue)
    after_a = embedder.texts_embedded
    ready_doc(b, queue)
    assert embedder.texts_embedded == 2 * after_a  # no cross-organization reuse


def test_scanned_pdf_ends_in_error_with_a_clear_message(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue, make_blank_pdf(), "scan.pdf")
    doc = c.get(f"/knowledge/{doc_id}").json()
    assert doc["status"] == "error" and "scan" in doc["error"] and doc["chunk_count"] == 0
    assert db.scalars(select(Job)).one().status == "error"
    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 202  # retry is allowed
    assert c.get(f"/knowledge/{doc_id}").json()["status"] == "pending"
    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 409  # already queued


def test_transient_embedding_failure_is_retried(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, embedder: CountingEmbedder, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    res = deposit(c, PDF_MEMO)
    doc_id = res.json()["id"]
    embedder.fail_times = 1
    with pytest.raises(EmbeddingError):  # the exception reaches RQ, which will retry
        queue.drain()
    doc = c.get(f"/knowledge/{doc_id}").json()
    assert doc["status"] == "error" and "nouvelle tentative" in doc["error"]
    queue.pending.append(__import__("uuid").UUID(doc_id))  # RQ retry
    queue.drain()
    assert c.get(f"/knowledge/{doc_id}").json()["status"] == "ready"
    calls = db.scalars(
        select(AiCall).where(AiCall.task == "embedding").order_by(AiCall.created_at)
    ).all()
    assert [x.success for x in calls][:2] == [False, True]


def test_wrong_embedding_dimension_is_rejected(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, embedder: CountingEmbedder, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    deposit(c, PDF_MEMO)
    embedder.bad_dim = True
    with pytest.raises(EmbeddingError, match="dimensions"):
        queue.drain()
    assert db.scalars(select(DocumentChunk)).all() == []  # nothing half-indexed


def test_queue_down_is_visible_not_silent(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    queue.down = True
    res = deposit(c, PDF_MEMO)
    assert res.status_code == 201 and res.json()["status"] == "error"
    queue.down = False
    assert c.post(f"/knowledge/{res.json()['id']}/reindex").status_code == 202


def test_job_for_a_deleted_document_is_a_noop(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = deposit(c, PDF_MEMO).json()["id"]
    assert c.delete(f"/knowledge/{doc_id}").status_code == 204
    queue.drain()  # must not raise


def test_delete_removes_index_file_and_object(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)
    assert db.scalars(select(DocumentChunk)).all() and storage.objects
    assert c.delete(f"/knowledge/{doc_id}").status_code == 204
    assert db.scalars(select(DocumentChunk)).all() == []
    assert (
        db.scalars(select(KnowledgeDocument)).all() == [] and db.scalars(select(File)).all() == []
    )
    assert storage.objects == {} and c.get(f"/knowledge/{doc_id}").status_code == 404


def test_rejects_other_types_infected_files_and_bad_kind(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scanner: FakeScanner,
    storage: MemoryStorage,
) -> None:
    c = signed_in_client(make_client, outbox)
    xlsx = io.BytesIO()
    from openpyxl import Workbook

    Workbook().save(xlsx)
    assert deposit(c, xlsx.getvalue(), "t.xlsx").status_code == 415
    assert deposit(c, b"\x89PNG\r\n\x1a\n" + b"0" * 30, "p.png").status_code == 415
    eicar = b"%PDF-1.4\nEICAR-STANDARD-ANTIVIRUS-TEST-FILE"
    assert deposit(c, eicar).json()["error"]["code"] == "infected_file"
    assert deposit(c, PDF_MEMO, kind="secret").status_code == 422
    assert storage.objects == {} and queue.pending == []


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/knowledge").status_code == 401
    assert anon.get("/knowledge/search", params={"q": "abc"}).status_code == 401
    assert deposit(anon, PDF_MEMO).status_code == 401


def test_tenancy_isolation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    doc_id = ready_doc(b, queue)
    assert a.get("/knowledge").json() == []
    assert a.get(f"/knowledge/{doc_id}").status_code == 404
    assert a.post(f"/knowledge/{doc_id}/reindex").status_code == 404
    assert a.delete(f"/knowledge/{doc_id}").status_code == 404
    assert b.get(f"/knowledge/{doc_id}").json()["status"] == "ready" and storage.objects


def test_reindex_after_a_model_change_re_embeds(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, embedder: CountingEmbedder, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)
    before = embedder.texts_embedded
    for chunk in db.scalars(select(DocumentChunk)):
        chunk.meta = {"embedding_model": "old/model"}
    db.commit()

    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 202
    queue.drain()
    assert embedder.texts_embedded > before  # old-model vectors are never reused
    assert {ch.meta["embedding_model"] for ch in db.scalars(select(DocumentChunk))} == {
        embedder.model
    }


def test_document_stuck_in_processing_can_be_reindexed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)
    db.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.id == doc_id)
        .values(status="processing", updated_at=datetime.now(UTC) - timedelta(minutes=5))
    )
    db.commit()
    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 409  # maybe still running

    db.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.id == doc_id)
        .values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )
    db.commit()
    assert c.post(f"/knowledge/{doc_id}/reindex").status_code == 202  # worker died long ago


def test_the_type_of_a_document_can_be_changed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    """Sent as « Ancien mémoire » instead of « Plan type »: corrected without sending it again."""
    c = signed_in_client(make_client, outbox)
    doc_id = ready_doc(c, queue)

    res = c.patch(f"/knowledge/{doc_id}", json={"kind": "memoir_template"})
    assert res.status_code == 200, res.text
    assert res.json()["kind"] == "memoir_template"
    assert res.json()["status"] == "ready"  # nothing to read again
    assert c.patch(f"/knowledge/{doc_id}", json={"kind": "nimporte"}).status_code == 422
    other = signed_in_client(make_client, outbox, 2)
    assert other.patch(f"/knowledge/{doc_id}", json={"kind": "other"}).status_code == 404
