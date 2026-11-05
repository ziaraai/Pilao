import hashlib
import io
import logging
import re
import unicodedata
import uuid
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import AuditLog, File, Organization, User
from app.domain.filetypes import ALLOWED, detect
from app.storage.antivirus import ScannerUnavailable, ScanTooLarge, VirusScanner
from app.storage.objects import ObjectStorage

logger = logging.getLogger("pilao.files")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f/\\]")
# Other spellings of a detected extension that must not get a second one ("photo.jpeg").
_EXTENSION_ALIASES = {"jpg": ("jpg", "jpeg", "jpe")}


def clean_filename(name: str | None, extension: str) -> str:
    """Display name only (never used in the storage key): no path, no control characters,
    no invisible Unicode formatting (a U+202E override makes a name read backwards)."""
    raw = (name or "").split("/")[-1].split("\\")[-1]
    raw = "".join(c for c in raw if unicodedata.category(c) != "Cf")
    base = _CONTROL.sub("_", raw).strip(" .")
    base = base[:200] or "document"
    suffixes = tuple(f".{e}" for e in _EXTENSION_ALIASES.get(extension, (extension,)))
    return base if base.lower().endswith(suffixes) else f"{base}.{extension}"


def scan_unavailable() -> ApiError:
    """Single refusal for every antivirus outage (unreachable daemon or not configured)."""
    return ApiError(503, "scan_unavailable", "Analyse antivirus indisponible, réessayez plus tard.")


def _check_quota(db: Session, size: int, quota: int) -> None:
    used = db.scalar(select(func.coalesce(func.sum(File.size_bytes), 0))) or 0
    if used + size > quota:
        raise ApiError(413, "quota_exceeded", "Espace de stockage de l'organisation dépassé.")


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
    user: User | None,
    fileobj: BinaryIO,
    filename: str | None,
    storage: ObjectStorage,
    scanner: VirusScanner,
    allowed_mimes: frozenset[str] | None = None,
    max_bytes: int | None = None,
) -> File:
    """Validate, scan and store one file. ``user`` is None for files a worker extracts on
    behalf of a user who has since been deleted."""
    s = get_settings()
    user_id = user.id if user is not None else None
    size, sha256 = _measure(fileobj, max_bytes or s.max_upload_bytes)
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

    _check_quota(db, size, s.org_storage_quota_bytes)  # fast refusal before scan and upload

    try:
        signature = scanner.scan(fileobj)
    except ScanTooLarge:
        raise ApiError(
            413,
            "too_large_for_scan",
            "Fichier trop volumineux pour l'analyse antivirus : découpez-le ou contactez-nous.",
        ) from None
    except ScannerUnavailable:
        logger.exception("antivirus unavailable: upload refused (fail closed)")
        raise scan_unavailable() from None
    fileobj.seek(0)
    if signature is not None:
        db.add(
            AuditLog(
                user_id=user_id,
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
        uploaded_by=user_id,
    )
    storage.put(record.storage_key, fileobj, kind.mime)
    try:
        # Concurrent uploads of one organization are serialized on its row until commit, so
        # two of them cannot both pass the quota check (re-done under the lock).
        db.execute(select(Organization.id).where(Organization.id == org.id).with_for_update())
        _check_quota(db, size, s.org_storage_quota_bytes)
        db.add(record)
        db.add(AuditLog(user_id=user_id, action="upload", entity="file", entity_id=record.id))
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.delete(record.storage_key)  # do not leave an orphan object behind
        except Exception:  # keep the original error; the orphan is left to the sweep job
            logger.exception("could not delete object %s (orphan to sweep)", record.storage_key)
        raise
    return record


def delete_file(db: Session, user: User | None, record: File, storage: ObjectStorage) -> None:
    key = record.storage_key
    db.add(
        AuditLog(
            user_id=user.id if user else None, action="delete", entity="file", entity_id=record.id
        )
    )
    db.delete(record)
    db.commit()
    try:
        storage.delete(key)
    except Exception:
        logger.exception("could not delete object %s (orphan to sweep)", key)


def store_generated(
    db: Session,
    org: Organization,
    user_id: uuid.UUID | None,
    data: bytes,
    filename: str,
    mime: str,
    extension: str,
    storage: ObjectStorage,
) -> File:
    """Store a document Pilao produced (no antivirus: it is our own output). The caller
    commits, and calls ``discard_object`` if that commit fails."""
    return store_generated_file(
        db, org, user_id, io.BytesIO(data), len(data), filename, mime, extension, storage
    )


def store_generated_file(
    db: Session,
    org: Organization,
    user_id: uuid.UUID | None,
    fileobj: BinaryIO,
    size: int,
    filename: str,
    mime: str,
    extension: str,
    storage: ObjectStorage,
    check_quota: bool = True,
) -> File:
    """Same, from a (possibly large, temporary) file read from its start."""
    s = get_settings()
    if check_quota:
        _check_quota(db, size, s.org_storage_quota_bytes)
    digest = hashlib.sha256()
    fileobj.seek(0)
    while chunk := fileobj.read(1024 * 1024):
        digest.update(chunk)
    fileobj.seek(0)
    record = File(
        id=uuid.uuid4(),
        storage_key=f"{org.id}/{uuid.uuid4()}",
        filename=clean_filename(filename, extension),
        mime=mime,
        size_bytes=size,
        sha256=digest.hexdigest(),
        uploaded_by=user_id,
    )
    storage.put(record.storage_key, fileobj, mime)
    db.execute(select(Organization.id).where(Organization.id == org.id).with_for_update())
    if check_quota:
        try:
            _check_quota(db, size, s.org_storage_quota_bytes)
        except ApiError:
            discard_object(storage, record.storage_key)
            raise
    db.add(record)
    db.flush()
    return record


def discard_object(storage: ObjectStorage, key: str) -> None:
    try:
        storage.delete(key)
    except Exception:  # the orphan is left to the sweep job
        logger.exception("could not delete object %s (orphan to sweep)", key)
