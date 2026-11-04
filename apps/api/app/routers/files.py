import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from sqlalchemy import any_, select

from app.core.config import get_settings
from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import (
    CompanyReference,
    ComplianceDocument,
    DceFile,
    DceVersion,
    File,
    KnowledgeDocument,
)
from app.schemas.files import DownloadUrlOut, FileOut
from app.services import files as svc
from app.storage.antivirus import ScannerUnavailable, VirusScanner, get_scanner
from app.storage.objects import ObjectStorage, get_storage

router = APIRouter(prefix="/files", tags=["files"])
Storage = Annotated[ObjectStorage, Depends(get_storage)]


def _scanner() -> VirusScanner:
    try:
        return get_scanner()
    except ScannerUnavailable:  # production without ClamAV configured: fail closed
        raise svc.scan_unavailable() from None


def _get(db: ScopedDb, file_id: uuid.UUID) -> File:
    record = db.get(File, file_id)
    if record is None:
        raise ApiError(404, "not_found", "Fichier introuvable.")
    return record


@router.post("", status_code=201)
def upload(
    file: UploadFile,
    ctx: CurrentAuth,
    db: ScopedDb,
    storage: Storage,
    scanner: Annotated[VirusScanner, Depends(_scanner)],
) -> FileOut:
    record = svc.upload_file(db, ctx.org, ctx.user, file.file, file.filename, storage, scanner)
    return FileOut.model_validate(record)


@router.get("")
def list_files(
    db: ScopedDb,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FileOut]:
    rows = db.scalars(select(File).order_by(File.created_at.desc()).limit(limit).offset(offset))
    return [FileOut.model_validate(r) for r in rows]


@router.get("/{file_id}")
def get_file(file_id: uuid.UUID, db: ScopedDb) -> FileOut:
    return FileOut.model_validate(_get(db, file_id))


@router.get("/{file_id}/download-url")
def download_url(file_id: uuid.UUID, db: ScopedDb, storage: Storage) -> DownloadUrlOut:
    """Short-lived signed URL: the API never streams the file itself."""
    record = _get(db, file_id)
    ttl = get_settings().signed_url_ttl_seconds
    return DownloadUrlOut(
        url=storage.signed_download_url(record.storage_key, record.filename, ttl), expires_in=ttl
    )


@router.delete("/{file_id}", status_code=204)
def delete(file_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage) -> Response:
    record = _get(db, file_id)
    # A file that backs an indexed document or an attestation must be deleted through its
    # owner, which also removes the derived data (search index...). Never leave orphans.
    for owner in (KnowledgeDocument, ComplianceDocument, DceFile):
        if db.scalar(select(owner.id).where(owner.file_id == record.id)) is not None:
            raise ApiError(
                409,
                "file_in_use",
                "Ce fichier est utilisé par un document : supprimez le document lui-même.",
            )
    deposited = select(DceVersion.id).where(any_(DceVersion.source_file_ids) == record.id)
    if db.scalar(deposited.limit(1)) is not None:
        raise ApiError(
            409, "file_in_use", "Ce fichier fait partie d'un DCE : supprimez le dossier lui-même."
        )
    # Reference photos are plain id lists (no foreign key): refuse rather than leave a dangling id.
    photo_of = select(CompanyReference.id).where(any_(CompanyReference.photo_file_ids) == record.id)
    if db.scalar(photo_of.limit(1)) is not None:
        raise ApiError(
            409,
            "file_in_use",
            "Ce fichier est une photo d'une référence : retirez-la de la référence d'abord.",
        )
    svc.delete_file(db, ctx.user, record, storage)
    return Response(status_code=204)
