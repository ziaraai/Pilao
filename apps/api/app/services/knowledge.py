import hashlib
import io
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.ai.calls import log_embedding_call
from app.ai.embeddings import Embedder, EmbeddingError
from app.ai.llm import LlmBudgetExceeded, ensure_budget
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    DocumentChunk,
    File,
    Job,
    KnowledgeDocument,
    Organization,
    User,
)
from app.documents.chunk import Chunk, chunk_blocks
from app.documents.convert import ConversionUnavailable, readable_form
from app.documents.extract import Block, ExtractionError, extract_docx, extract_pdf
from app.domain.filetypes import DOC, DOCX, ODT, PDF
from app.services import files as files_svc
from app.services.jobs import set_job_status
from app.storage.antivirus import VirusScanner
from app.storage.objects import ObjectStorage
from app.workers.queue import INDEX_JOB_TIMEOUT_SECONDS, JobQueue

logger = logging.getLogger("pilao.knowledge")

JOB_KIND = "index_knowledge_document"
ALLOWED_MIMES = frozenset({PDF.mime, DOCX.mime, ODT.mime, DOC.mime})


def document_blocks(fileobj: BinaryIO, mime: str) -> list[Block]:
    """PDF and DOCX directly; ODT and DOC through a DOCX, which keeps the headings."""
    if mime == PDF.mime:
        return extract_pdf(fileobj)
    if mime in (ODT.mime, DOC.mime):
        kind = ODT if mime == ODT.mime else DOC
        try:
            converted, _ = readable_form(fileobj.read(), kind, text_target="docx")
        except ConversionUnavailable as exc:
            raise ExtractionError(f"Lecture impossible : {exc}") from exc
        return extract_docx(io.BytesIO(converted))
    return extract_docx(fileobj)


EMBED_BATCH = 64


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _enqueue(db: Session, doc: KnowledgeDocument, queue: JobQueue) -> None:
    job = Job(kind=JOB_KIND, ref_id=doc.id, org_id=doc.org_id, status="pending")
    db.add(job)
    doc.status, doc.error = "pending", None
    db.commit()
    try:
        queue.enqueue_index_document(doc.id)
    except Exception:
        logger.exception("could not enqueue indexing of %s", doc.id)
        doc.status, doc.error = "error", "File d'attente indisponible. Réessayez plus tard."
        job.status, job.error, job.finished_at = "error", "enqueue failed", _now()
        db.commit()


def create_document(
    db: Session,
    org: Organization,
    user: User,
    fileobj: BinaryIO,
    filename: str | None,
    kind: str,
    title: str | None,
    storage: ObjectStorage,
    scanner: VirusScanner,
    queue: JobQueue,
) -> KnowledgeDocument:
    record = files_svc.upload_file(
        db, org, user, fileobj, filename, storage, scanner, allowed_mimes=ALLOWED_MIMES
    )
    doc = KnowledgeDocument(
        file_id=record.id,
        kind=kind,
        title=(title or record.filename).strip()[:300],
        status="pending",
    )
    db.add(doc)
    db.flush()
    _enqueue(db, doc, queue)
    return doc


def reindex_document(db: Session, doc: KnowledgeDocument, queue: JobQueue) -> None:
    # A worker killed mid-job (out of memory, redeploy) never resets "processing": once the
    # job timeout is long past, the document must not stay locked forever.
    stale = doc.status == "processing" and doc.updated_at < _now() - timedelta(
        seconds=2 * INDEX_JOB_TIMEOUT_SECONDS
    )
    if doc.status in ("pending", "processing") and not stale:
        raise ApiError(409, "already_running", "L'indexation est déjà en cours.")
    _enqueue(db, doc, queue)


def delete_document(
    db: Session, user: User, doc: KnowledgeDocument, storage: ObjectStorage
) -> None:
    """US-1.4 CA3: deleting a document also deletes its index (chunks), file and object."""
    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.source_type == "knowledge", DocumentChunk.source_id == doc.id
        )
    )
    record = db.get_one(File, doc.file_id)
    db.flush()
    files_svc.delete_file(db, user, record, storage)  # cascades to the document row


def _set_job(db: Session, doc_id: uuid.UUID, status: str, error: str | None = None) -> None:
    set_job_status(db, JOB_KIND, doc_id, status, error)


def _embed_chunks(
    db: Session, org_id: uuid.UUID, chunks: list[Chunk], embedder: Embedder
) -> list[list[float]]:
    """Embeddings for ``chunks``; identical text already indexed *in this org* is reused.

    Only vectors made by the current model are reused: after a model change, a reindex
    really re-embeds instead of mixing two vector spaces.
    """
    hashes = [_hash(c.content) for c in chunks]
    known: dict[str, list[float]] = {}
    rows = db.execute(
        select(DocumentChunk.content_hash, DocumentChunk.embedding)
        .where(
            DocumentChunk.org_id == org_id,
            DocumentChunk.content_hash.in_(set(hashes)),
            DocumentChunk.meta["embedding_model"].astext == embedder.model,
        )
        .ext(distinct_on(DocumentChunk.content_hash))
    )
    for content_hash, vector in rows:
        known[content_hash] = [float(x) for x in vector]

    missing = [i for i, h in enumerate(hashes) if h not in known]
    if missing:
        ensure_budget(db, org_id)
    dim = get_settings().embedding_dim
    for start in range(0, len(missing), EMBED_BATCH):
        batch = missing[start : start + EMBED_BATCH]
        began = time.monotonic()
        try:
            result = embedder.embed([chunks[i].content for i in batch])
        except EmbeddingError as exc:
            log_embedding_call(
                db, org_id, None, int((time.monotonic() - began) * 1000), embedder.model, str(exc)
            )
            db.commit()
            raise
        log_embedding_call(db, org_id, result, int((time.monotonic() - began) * 1000), result.model)
        db.commit()  # the call is paid: its journal row must survive any later failure
        if len(result.vectors) != len(batch) or any(len(v) != dim for v in result.vectors):
            raise EmbeddingError(f"unexpected embedding shape (expected {dim} dimensions)")
        for i, vector in zip(batch, result.vectors, strict=True):
            known[hashes[i]] = vector
    return [known[h] for h in hashes]


def run_index_document(
    db: Session, doc_id: uuid.UUID, storage: ObjectStorage, embedder: Embedder
) -> None:
    """Extract, chunk, embed and store one document. Idempotent: it replaces existing chunks."""
    doc = db.get(KnowledgeDocument, doc_id)  # unscoped worker session: look up by id only
    if doc is None:
        return  # deleted while the job was waiting in the queue
    org_id = doc.org_id
    scope_session(db, org_id)  # from here, defense in depth: only this org's rows are visible
    record = db.get_one(File, doc.file_id)
    doc.status, doc.error = "processing", None
    _set_job(db, doc.id, "running")
    db.commit()

    try:
        fileobj = storage.get(record.storage_key)
        try:
            blocks = document_blocks(fileobj, record.mime)
        finally:
            fileobj.close()
        chunks = chunk_blocks(blocks)
        if not chunks:
            raise ExtractionError("Aucun texte exploitable dans ce document.")
        vectors = _embed_chunks(db, org_id, chunks, embedder)
    except (ExtractionError, LlmBudgetExceeded) as exc:  # permanent: shown to the user
        db.rollback()
        doc = db.get_one(KnowledgeDocument, doc_id)
        doc.status, doc.error = "error", str(exc)
        _set_job(db, doc_id, "error", str(exc))
        db.commit()
        return
    except Exception:
        db.rollback()
        doc = db.get_one(KnowledgeDocument, doc_id)
        doc.status, doc.error = "error", "Indexation interrompue, nouvelle tentative en cours."
        _set_job(db, doc_id, "error", "transient failure")
        db.commit()
        raise  # lets RQ retry

    # The session does not expire on commit: reload and lock the row, so that a document
    # deleted by the user while it was being indexed is not resurrected as orphan chunks.
    fresh = db.get(KnowledgeDocument, doc_id, populate_existing=True, with_for_update=True)
    if fresh is None:
        db.commit()  # keep the ai_calls journal, write nothing else
        return
    db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.source_type == "knowledge", DocumentChunk.source_id == doc_id
        )
    )
    for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        db.add(
            DocumentChunk(
                org_id=org_id,
                source_type="knowledge",
                source_id=doc_id,
                position=position,
                page_from=chunk.page_from,
                page_to=chunk.page_to,
                heading=chunk.heading,
                content=chunk.content,
                content_hash=_hash(chunk.content),
                tokens=chunk.tokens,
                embedding=vector,
                meta={"embedding_model": embedder.model},
            )
        )
    doc = fresh
    doc.status, doc.error, doc.chunk_count = "ready", None, len(chunks)
    pages = [b.page for b in blocks if b.page is not None]
    doc.page_count = max(pages) if pages else None
    _set_job(db, doc_id, "done")
    db.commit()


def search_chunks(
    db: Session, org: Organization, embedder: Embedder, query: str, k: int = 5
) -> list[tuple[DocumentChunk, str, float]]:
    """Top-k passages of this organization's ready documents, most similar first.

    The ``org_id`` filter is part of the SQL (docs/09-securite-rgpd.md), in addition to the
    session scope: it is never applied after the vector search.
    """
    ensure_budget(db, org.id)
    began = time.monotonic()
    result = embedder.embed([query])
    log_embedding_call(db, org.id, result, int((time.monotonic() - began) * 1000), result.model)
    distance = DocumentChunk.embedding.cosine_distance(result.vectors[0])
    rows = db.execute(
        select(DocumentChunk, KnowledgeDocument.title, distance)
        .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.source_id)
        .where(
            DocumentChunk.org_id == org.id,
            DocumentChunk.source_type == "knowledge",
            KnowledgeDocument.status == "ready",
        )
        .order_by(distance)
        .limit(k)
    ).all()
    db.commit()
    return [(chunk, title, 1.0 - float(dist)) for chunk, title, dist in rows]
