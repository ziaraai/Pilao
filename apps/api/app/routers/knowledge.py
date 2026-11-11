import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from sqlalchemy import select

from app.ai.embeddings import Embedder, EmbeddingError, get_embedder
from app.ai.llm import LlmBudgetExceeded
from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import AuditLog, KnowledgeDocument
from app.routers.files import Storage, _scanner
from app.schemas.knowledge import (
    DocumentKind,
    KnowledgeDocumentOut,
    KnowledgeKindIn,
    SearchHitOut,
)
from app.services import knowledge as svc
from app.storage.antivirus import VirusScanner
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _get(db: ScopedDb, doc_id: uuid.UUID) -> KnowledgeDocument:
    doc = db.get(KnowledgeDocument, doc_id)
    if doc is None:
        raise ApiError(404, "not_found", "Document introuvable.")
    return doc


@router.post("", status_code=201)
def upload_document(
    file: UploadFile,
    kind: Annotated[DocumentKind, Form()],
    ctx: CurrentAuth,
    db: ScopedDb,
    storage: Storage,
    scanner: Annotated[VirusScanner, Depends(_scanner)],
    queue: Queue,
    title: Annotated[str | None, Form(max_length=300)] = None,
) -> KnowledgeDocumentOut:
    """Deposit a PDF/DOCX (50 MB max). It is indexed in the background; poll its status."""
    doc = svc.create_document(
        db, ctx.org, ctx.user, file.file, file.filename, kind, title, storage, scanner, queue
    )
    return KnowledgeDocumentOut.model_validate(doc)


@router.get("")
def list_documents(db: ScopedDb) -> list[KnowledgeDocumentOut]:
    rows = db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc()))
    return [KnowledgeDocumentOut.model_validate(r) for r in rows]


@router.get("/search")
def search(
    q: Annotated[str, Query(min_length=2, max_length=500)],
    ctx: CurrentAuth,
    db: ScopedDb,
    embedder: Annotated[Embedder, Depends(get_embedder)],
    k: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[SearchHitOut]:
    try:
        hits = svc.search_chunks(db, ctx.org, embedder, q, k)
    except LlmBudgetExceeded:
        raise ApiError(429, "ai_budget_exceeded", "Budget IA mensuel atteint.") from None
    except EmbeddingError:
        raise ApiError(503, "embedding_unavailable", "Recherche indisponible, réessayez.") from None
    return [
        SearchHitOut(
            chunk_id=c.id,
            document_id=c.source_id,
            document_title=title,
            heading=c.heading,
            page_from=c.page_from,
            page_to=c.page_to,
            content=c.content,
            score=round(score, 4),
        )
        for c, title, score in hits
    ]


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, db: ScopedDb) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut.model_validate(_get(db, doc_id))


@router.patch("/{doc_id}")
def change_kind(
    doc_id: uuid.UUID, data: KnowledgeKindIn, ctx: CurrentAuth, db: ScopedDb
) -> KnowledgeDocumentOut:
    """A document sent with the wrong type (« Ancien mémoire » for the « Plan type »)."""
    doc = _get(db, doc_id)
    doc.kind = data.kind
    db.add(
        AuditLog(
            user_id=ctx.user.id, action="update", entity="knowledge_document", entity_id=doc.id
        )
    )
    db.commit()
    return KnowledgeDocumentOut.model_validate(doc)


@router.post("/{doc_id}/reindex", status_code=202)
def reindex(doc_id: uuid.UUID, db: ScopedDb, queue: Queue) -> KnowledgeDocumentOut:
    doc = _get(db, doc_id)
    svc.reindex_document(db, doc, queue)
    return KnowledgeDocumentOut.model_validate(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage
) -> Response:
    svc.delete_document(db, ctx.user, _get(db, doc_id), storage)
    return Response(status_code=204)
