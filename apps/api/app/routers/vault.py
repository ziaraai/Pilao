import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from sqlalchemy import select

from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import ComplianceDocument
from app.domain import vault as rules
from app.routers.files import Storage, _scanner
from app.schemas.vault import ComplianceDocOut, ConfirmIn, HelpLinkOut, Kind, SummaryOut
from app.services import vault as svc
from app.storage.antivirus import VirusScanner
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(prefix="/vault", tags=["vault"])
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _get(db: ScopedDb, doc_id: uuid.UUID) -> ComplianceDocument:
    doc = db.get(ComplianceDocument, doc_id)
    if doc is None:
        raise ApiError(404, "not_found", "Document introuvable.")
    return doc


@router.post("", status_code=201)
def upload(
    file: UploadFile,
    ctx: CurrentAuth,
    db: ScopedDb,
    storage: Storage,
    scanner: Annotated[VirusScanner, Depends(_scanner)],
    queue: Queue,
    kind: Annotated[Kind | None, Form()] = None,
) -> ComplianceDocOut:
    """Deposit a PDF / PNG / JPEG attestation. The AI pre-fills it; you must confirm it."""
    doc = svc.create_document(
        db, ctx.org, ctx.user, file.file, file.filename, kind, storage, scanner, queue
    )
    return svc.to_out(doc, ctx.org, rules.paris_today())


@router.get("")
def list_documents(
    ctx: CurrentAuth,
    db: ScopedDb,
    status: Annotated[
        str | None, Query(pattern="^(pending_review|valid|expiring|expired|mismatch)$")
    ] = None,
) -> list[ComplianceDocOut]:
    today = rules.paris_today()
    docs = [
        svc.to_out(d, ctx.org, today)
        for d in db.scalars(
            select(ComplianceDocument).order_by(ComplianceDocument.created_at.desc())
        )
    ]
    return [d for d in docs if status is None or d.status == status]


# Fixed paths are declared before "/{doc_id}".
@router.get("/summary")
def get_summary(ctx: CurrentAuth, db: ScopedDb) -> SummaryOut:
    return svc.summary(db, ctx.org, rules.paris_today())


@router.get("/help-links")
def help_links(_: CurrentAuth) -> list[HelpLinkOut]:
    return [HelpLinkOut(kind=k, **v) for k, v in rules.HELP_LINKS.items()]


@router.get("/{doc_id}")
def get_document(doc_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb) -> ComplianceDocOut:
    return svc.to_out(_get(db, doc_id), ctx.org, rules.paris_today())


@router.put("/{doc_id}/confirm")
def confirm(doc_id: uuid.UUID, data: ConfirmIn, ctx: CurrentAuth, db: ScopedDb) -> ComplianceDocOut:
    doc = svc.confirm(db, ctx.org, ctx.user, _get(db, doc_id), data)
    return svc.to_out(doc, ctx.org, rules.paris_today())


@router.post("/{doc_id}/reread", status_code=202)
def reread(doc_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, queue: Queue) -> ComplianceDocOut:
    doc = _get(db, doc_id)
    svc.reread(db, doc, queue)
    return svc.to_out(doc, ctx.org, rules.paris_today())


@router.delete("/{doc_id}", status_code=204)
def delete(doc_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage) -> Response:
    svc.delete_document(db, ctx.user, _get(db, doc_id), storage)
    return Response(status_code=204)
