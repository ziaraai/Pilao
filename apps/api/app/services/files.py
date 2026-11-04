import hashlib
import logging
import re
import uuid
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import AuditLog, File, Organization, User
from app.domain.filetypes import ALLOWED, detect
from app.storage.antivirus import ScannerUnavailable, VirusScanner
from app.storage.objects import ObjectStorage

logger = logging.getLogger("pilao.files")
_CONTROL = re.compile(r"[\x00-\x1f\x7f/\\]")


def clean_filename(name: str | None, extension: str) -> str:
    """Display name only (never used in the storage key): no path, no control characters."""
    base = _CONTROL.sub("_", (name or "").split("/")[-1].split("\\")[-1]).strip(" .")
    base = base[:200] or "document"
    return base if base.lower().endswith(f".{extension}") else f"{base}.{extension}"


def _measure(fileobj: BinaryIO, limit: int) -> tuple[int, str]:
    """Stream the file once: size (bounded) and SHA-256."""
    digest, size = hashlib.sha256(), 0
    fileobj.seek(0)
    while chunk := fileobj.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ApiError(
                413, "file_too_large", f"Fichier trop volumineux ({limit // 2**20} Mo maximum)."
            )
        digest.update(chunk)
    fileobj.seek(0)
    return size, digest.hexdigest()


def upload_file(
    db: Session,
    org: Organization,
    user: User,
    fileobj: BinaryIO,
    filename: str | None,
    storage: ObjectStorage,
    scanner: VirusScanner,
    allowed_mimes: frozenset[str] | None = None,
) -> File:
    s = get_settings()
    size, sha256 = _measure(fileobj, s.max_upload_bytes)
    if size == 0:
        raise ApiError(422, "empty_file", "Le fichier est vide.")
    kind = detect(fileobj)
    if kind is None:
        raise ApiError(
            415,
            "unsupported_type",
            "Format non accepté. Formats : PDF, DOCX, XLSX, ZIP, PNG, JPEG.",
        )

    if allowed_mimes is not None and kind.mime not in allowed_mimes:
        accepted = ", ".join(t.extension.upper() for t in ALLOWED if t.mime in allowed_mimes)
        raise ApiError(415, "unsupported_type", f"Format non accepté pour ce dépôt ({accepted}).")

    used = db.scalar(select(func.coalesce(func.sum(File.size_bytes), 0))) or 0
    if used + size > s.org_storage_quota_bytes:
        raise ApiError(413, "quota_exceeded", "Espace de stockage de l'organisation dépassé.")

    try:
        signature = scanner.scan(fileobj)
    except ScannerUnavailable:
        logger.exception("antivirus unavailable: upload refused (fail closed)")
        raise ApiError(
            503, "scan_unavailable", "Analyse antivirus indisponible, réessayez plus tard."
        ) from None
    fileobj.seek(0)
    if signature is not None:
        db.add(
            AuditLog(
                user_id=user.id,
                action="upload_blocked",
                entity="file",
                meta={"signature": signature, "sha256": sha256, "filename": (filename or "")[:200]},
            )
        )
        db.commit()
        raise ApiError(422, "infected_file", "Fichier refusé : un virus a été détecté.")

    record = File(
        id=uuid.uuid4(),
        storage_key=f"{org.id}/{uuid.uuid4()}",
        filename=clean_filename(filename, kind.extension),
        mime=kind.mime,
        size_bytes=size,
        sha256=sha256,
        uploaded_by=user.id,
    )
    storage.put(record.storage_key, fileobj, kind.mime)
    try:
        db.add(record)
        db.add(AuditLog(user_id=user.id, action="upload", entity="file", entity_id=record.id))
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(record.storage_key)  # do not leave an orphan object behind
        raise
    return record


def delete_file(db: Session, user: User, record: File, storage: ObjectStorage) -> None:
    key = record.storage_key
    db.add(AuditLog(user_id=user.id, action="delete", entity="file", entity_id=record.id))
    db.delete(record)
    db.commit()
    try:
        storage.delete(key)
    except Exception:
        logger.exception("could not delete object %s (orphan to sweep)", key)
