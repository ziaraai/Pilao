import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import Bid, File, GeneratedDocument, Memoir
from app.exports.dc_forms import FORMS
from app.schemas.documents import (
    ChapterToComplete,
    DocumentKindOut,
    ExportCheckOut,
    ExportIn,
    GeneratedDocumentOut,
    MissingRequirement,
)
from app.services import documents as svc
from app.services import exports
from app.storage.objects import ObjectStorage, get_storage
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["documents"])
Storage = Annotated[ObjectStorage, Depends(get_storage)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]

DESCRIPTIONS = {
    "dc1": "Lettre de candidature : acheteur, objet, identité, engagements à cocher et signer.",
    "dc2": "Déclaration du candidat : identité, chiffre d'affaires, moyens, preuves disponibles.",
    "staff_list": "Personnel et qualifications déclarés dans votre profil.",
    "equipment_list": "Matériel déclaré dans votre profil.",
    "references_list": "Vos références, celles retenues pour le mémoire en premier.",
    "planning": "Étapes du marché avec les dates connues du DCE, le reste à compléter.",
}


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


def document_out(db: ScopedDb, doc: GeneratedDocument) -> GeneratedDocumentOut:
    record = db.get(File, doc.file_id) if doc.file_id else None
    return GeneratedDocumentOut(
        id=doc.id,
        kind=doc.kind,
        status=doc.status,
        error=doc.error,
        file_id=record.id if record else None,
        filename=record.filename if record else None,
        size_bytes=record.size_bytes if record else None,
        to_complete=doc.to_complete,
        warnings=doc.warnings,
        memoir_id=doc.memoir_id,
        created_at=doc.created_at,
    )


@router.get("/bids/{bid_id}/documents")
def list_documents(bid_id: uuid.UUID, db: ScopedDb) -> list[DocumentKindOut]:
    """US-4.5: the pre-filled documents of the bid, with the latest version of each."""
    bid = _bid(db, bid_id)
    latest: dict[str, GeneratedDocument] = {}
    for doc in db.scalars(
        select(GeneratedDocument)
        .where(GeneratedDocument.bid_id == bid.id, GeneratedDocument.kind.in_(list(FORMS)))
        .order_by(GeneratedDocument.created_at.desc())
    ):
        latest.setdefault(doc.kind, doc)
    return [
        DocumentKindOut(
            kind=kind,
            label=label,
            description=DESCRIPTIONS[kind],
            latest=document_out(db, latest[kind]) if kind in latest else None,
        )
        for kind, (label, _) in FORMS.items()
    ]


@router.post("/bids/{bid_id}/documents/{kind}", status_code=201)
def generate_document(
    bid_id: uuid.UUID, kind: str, ctx: CurrentAuth, db: ScopedDb, storage: Storage
) -> GeneratedDocumentOut:
    """Build the document now from the profile and the analysed DCE (a few milliseconds)."""
    doc = svc.generate_form(db, ctx.org, ctx.user, _bid(db, bid_id), kind, storage)
    return document_out(db, doc)


def _memoir(db: ScopedDb, memoir_id: uuid.UUID) -> Memoir:
    memoir = db.get(Memoir, memoir_id)
    if memoir is None:
        raise ApiError(404, "not_found", "Mémoire introuvable.")
    return memoir


@router.get("/memoirs/{memoir_id}/export-check")
def export_check(memoir_id: uuid.UUID, db: ScopedDb) -> ExportCheckOut:
    """US-4.6 CA4: what remains before exporting, shown to the user first."""
    check = exports.export_check(db, _memoir(db, memoir_id))
    return ExportCheckOut(
        warnings=check.warnings,
        to_complete=[
            ChapterToComplete(section_id=s.id, title=s.title, items=items)
            for s, items in check.to_complete
        ],
        missing_requirements=[MissingRequirement(ref=r.ref, text=r.text) for r in check.missing],
        not_drafted=check.not_drafted,
        conformity_status=check.conformity_status,
        estimated_pages=check.pages,
        max_pages=check.max_pages,
    )


@router.post("/memoirs/{memoir_id}/exports", status_code=202)
def request_export(
    memoir_id: uuid.UUID, data: ExportIn, ctx: CurrentAuth, db: ScopedDb, queue: Queue
) -> GeneratedDocumentOut:
    """Word, PDF or complete ZIP, built in the background: poll the returned document."""
    doc = exports.request_export(
        db, ctx.user, _memoir(db, memoir_id), data.format, data.acknowledge_warnings, queue
    )
    return document_out(db, doc)


@router.get("/memoirs/{memoir_id}/exports")
def list_exports(memoir_id: uuid.UUID, db: ScopedDb) -> list[GeneratedDocumentOut]:
    memoir = _memoir(db, memoir_id)
    return [
        document_out(db, d)
        for d in db.scalars(
            select(GeneratedDocument)
            .where(GeneratedDocument.memoir_id == memoir.id)
            .order_by(GeneratedDocument.created_at.desc())
            .limit(30)
        )
    ]


@router.get("/generated-documents/{document_id}")
def read_document(document_id: uuid.UUID, db: ScopedDb) -> GeneratedDocumentOut:
    doc = db.get(GeneratedDocument, document_id)
    if doc is None:
        raise ApiError(404, "not_found", "Document introuvable.")
    return document_out(db, doc)
