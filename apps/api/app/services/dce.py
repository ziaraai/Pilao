"""DCE deposit and processing (US-3.1): versions, safe expansion, typing, differences."""

import hashlib
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Mailer
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import Bid, DceFile, DcePage, DceVersion, File, Job, Organization, User
from app.documents.archive import ArchiveError, Member, expand
from app.documents.ocr import OcrEngine
from app.documents.pages import extract_pages
from app.domain.dce import kind_from_content, kind_from_filename, normalize
from app.domain.filetypes import (
    DOCX,
    JPEG,
    PDF,
    PNG,
    SHEETS_TO_CONVERT,
    TEXT_TO_CONVERT,
    XLSX,
    ZIP,
    detect,
)
from app.services import files as files_svc
from app.services.jobs import set_job_status
from app.storage.antivirus import VirusScanner
from app.storage.objects import ObjectStorage
from app.workers.queue import DCE_JOB_TIMEOUT_SECONDS, JobQueue

logger = logging.getLogger("pilao.dce")
JOB_KIND = "process_dce"
DEPOSIT_MIMES = frozenset(
    {PDF.mime, DOCX.mime, XLSX.mime, ZIP.mime, PNG.mime, JPEG.mime}
    | {t.mime for t in (*TEXT_TO_CONVERT, *SHEETS_TO_CONVERT)}  # read after conversion
)
MEMBER_MIMES = DEPOSIT_MIMES - {ZIP.mime}
MAX_FILES_PER_DEPOSIT = 50


class _Permanent(Exception):
    """Processing cannot succeed by retrying; the message is shown to the user."""


# ---------- deposit -----------------------------------------------------------------------


def create_version(
    db: Session,
    org: Organization,
    user: User,
    bid: Bid,
    uploads: list[tuple[BinaryIO, str | None]],
    storage: ObjectStorage,
    scanner: VirusScanner,
    queue: JobQueue,
    *,
    origin: str = "deposit",
    source_url: str | None = None,
) -> DceVersion:
    """A new version of the DCE from deposited files, or from the robot's ZIP (``origin``
    ``retrieval`` or ``update``, spec « Récupération des DCE »): the same checks either way."""
    if not uploads:
        raise ApiError(422, "no_file", "Déposez au moins un fichier.")
    if len(uploads) > MAX_FILES_PER_DEPOSIT:
        raise ApiError(
            422, "too_many_files", f"{MAX_FILES_PER_DEPOSIT} fichiers maximum par dépôt."
        )
    busy = db.scalar(
        select(DceVersion.id).where(
            DceVersion.bid_id == bid.id,
            DceVersion.status.in_(("pending", "processing")),
            # A worker killed after its last retry never finishes: do not block forever.
            DceVersion.updated_at
            > datetime.now(UTC) - timedelta(seconds=2 * DCE_JOB_TIMEOUT_SECONDS),
        )
    )
    if busy is not None:
        raise ApiError(409, "dce_processing", "Un dépôt est déjà en cours de traitement.")

    stored: list[File] = []
    try:
        for fileobj, filename in uploads:
            stored.append(
                files_svc.upload_file(
                    db,
                    org,
                    user,
                    fileobj,
                    filename,
                    storage,
                    scanner,
                    allowed_mimes=DEPOSIT_MIMES,
                    max_bytes=get_settings().max_dce_upload_bytes,
                )
            )
        number = (
            db.scalar(select(func.max(DceVersion.version)).where(DceVersion.bid_id == bid.id)) or 0
        ) + 1
        version = DceVersion(
            id=uuid.uuid4(),  # needed now: the Job row below references it before the flush
            bid_id=bid.id,
            version=number,
            uploaded_by=user.id,
            status="pending",
            source_file_ids=[f.id for f in stored],
            origin=origin,
            source_url=source_url,
        )
        db.add(version)
        db.add(Job(kind=JOB_KIND, ref_id=version.id, org_id=org.id, status="pending"))
        db.commit()
    except IntegrityError:  # two deposits raced for the same version number
        db.rollback()
        _delete_files(db, user, stored, storage)
        raise ApiError(409, "dce_processing", "Un dépôt est déjà en cours de traitement.") from None
    except Exception:
        db.rollback()
        _delete_files(db, user, stored, storage)  # no half deposit
        raise
    try:
        queue.enqueue_process_dce(version.id)
    except Exception:
        logger.exception("could not enqueue DCE version %s", version.id)
        version.status, version.error = "error", "File d'attente indisponible. Redéposez plus tard."
        set_job_status(db, JOB_KIND, version.id, "error", version.error)
        db.commit()
    return version


def _delete_files(
    db: Session, user: User | None, records: list[File], storage: ObjectStorage
) -> None:
    for record in records:
        current = db.get(File, record.id)
        if current is not None:
            files_svc.delete_file(db, user, current, storage)


# ---------- processing (worker) -----------------------------------------------------------


@dataclass
class _Ctx:
    db: Session
    org: Organization
    user: User | None
    version: DceVersion
    storage: ObjectStorage
    scanner: VirusScanner
    skipped: list[dict[str, Any]]
    seen: dict[str, str]  # stored path -> sha256
    ocr: OcrEngine | None


def _members(record: File, data: BinaryIO, skipped: list[dict[str, Any]]) -> Iterator[Member]:
    if record.mime == ZIP.mime:
        members, archive_skipped = expand(data, "")
        yield from members
        skipped.extend({"path": s.path, "reason": s.reason} for s in archive_skipped)
    else:
        size = data.seek(0, 2)
        data.seek(0)
        yield Member(record.filename, data, size)


def _sha256(data: BinaryIO) -> str:
    digest = hashlib.sha256()
    data.seek(0)
    while chunk := data.read(1024 * 1024):
        digest.update(chunk)
    data.seek(0)
    return digest.hexdigest()


def _store_member(ctx: _Ctx, member: Member, source_name: str) -> None:
    path = member.path
    if path in ctx.seen:  # same relative path twice (two archives, two uploads...)
        digest = _sha256(member.data)
        if digest == ctx.seen[path]:
            ctx.skipped.append({"path": path, "reason": "doublon d'un fichier déjà déposé"})
            return  # the very same entry twice: nothing to add
        path, n = f"{source_name}/{member.path}", 2
        while path in ctx.seen:  # different content: keep it under a unique path
            path, n = f"{source_name} ({n})/{member.path}", n + 1
    kind = detect(member.data)
    if kind is None or kind.mime not in MEMBER_MIMES:
        ctx.skipped.append({"path": path, "reason": "format non pris en charge"})
        return
    try:
        record = files_svc.upload_file(
            ctx.db,
            ctx.org,
            ctx.user,
            member.data,
            path.rsplit("/", 1)[-1],
            ctx.storage,
            ctx.scanner,
            allowed_mimes=MEMBER_MIMES,
            max_bytes=get_settings().max_dce_upload_bytes,
        )
    except ApiError as exc:
        if exc.code == "scan_unavailable":
            raise  # transient: the whole job is retried
        if exc.code == "quota_exceeded":
            raise _Permanent("Espace de stockage de l'organisation dépassé.") from exc
        ctx.skipped.append({"path": path, "reason": exc.message})
        return
    ctx.seen[path] = record.sha256  # same content under two names is kept: never drop silently
    extraction = extract_pages(member.data, record.mime, ctx.ocr)
    typing = kind_from_filename(path)
    if typing.source == "none" and extraction.pages:
        typing = kind_from_content("\n".join(p.text for p in extraction.pages[:2]))
    dce_file = DceFile(
        id=uuid.uuid4(),  # the pages below reference it before the flush
        dce_version_id=ctx.version.id,
        file_id=record.id,
        path=path,
        sha256=record.sha256,
        detected_kind=typing.kind,
        kind_source=typing.source,
        page_count=len(extraction.pages) if extraction.paginated and extraction.pages else None,
        paginated=extraction.paginated,
        ocr_used=extraction.ocr_used,
        text_status=extraction.status,
        text_error=extraction.error,
    )
    ctx.db.add(dce_file)
    ctx.db.add_all(
        DcePage(dce_file_id=dce_file.id, page=p.page, text=p.text, ocr_used=p.ocr_used)
        for p in extraction.pages
    )
    ctx.db.commit()


def _cleanup(db: Session, user: User | None, version_id: uuid.UUID, storage: ObjectStorage) -> None:
    """Remove what a previous (failed) attempt extracted, so that a retry starts clean."""
    records = db.scalars(
        select(File)
        .join(DceFile, DceFile.file_id == File.id)
        .where(DceFile.dce_version_id == version_id)
    ).all()
    for record in records:
        files_svc.delete_file(db, user, record, storage)  # cascades to dce_files


def run_process_dce(
    db: Session,
    version_id: uuid.UUID,
    storage: ObjectStorage,
    scanner: VirusScanner,
    ocr: OcrEngine | None = None,
    queue: JobQueue | None = None,
    mailer: Mailer | None = None,
) -> None:
    """Expand, store, extract and type the pieces; then start the AI analysis (if a queue).
    An update found by the robot's watch is not analysed: its mail says so (``mailer``)."""
    version = db.get(DceVersion, version_id)
    if version is None:
        return
    scope_session(db, version.org_id)
    org = db.get_one(Organization, version.org_id)
    user = db.get(User, version.uploaded_by) if version.uploaded_by else None
    version.status, version.error = "processing", None
    set_job_status(db, JOB_KIND, version_id, "running")
    db.commit()

    ctx = _Ctx(db, org, user, version, storage, scanner, [], {}, ocr)
    try:
        _cleanup(db, user, version_id, storage)
        for file_id in version.source_file_ids:
            record = db.get(File, file_id)
            if record is None:
                raise _Permanent("Un fichier du dépôt a été supprimé : redéposez le DCE.")
            data = storage.get(record.storage_key)
            try:
                for member in _members(record, data, ctx.skipped):
                    try:
                        _store_member(ctx, member, record.filename)
                    finally:
                        if member.data is not data:
                            member.data.close()
            finally:
                data.close()
        if not ctx.seen:
            raise _Permanent("Aucun fichier exploitable dans ce dépôt.")
    except (ArchiveError, _Permanent) as exc:
        db.rollback()
        _cleanup(db, user, version_id, storage)
        _finish(db, version_id, "error", str(exc), ctx.skipped)
        return
    except Exception:
        db.rollback()
        _finish(
            db,
            version_id,
            "processing",  # a retry is scheduled: the version is not finished
            "Traitement interrompu, nouvelle tentative en cours.",
            ctx.skipped,
        )
        raise  # lets RQ retry

    fresh = db.get(DceVersion, version_id, populate_existing=True)
    if fresh is None:  # the bid was deleted meanwhile
        return
    fresh.diff, fresh.diff_summary = compute_diff(db, fresh)
    _finish(db, version_id, "ready", None, ctx.skipped)
    if fresh.origin == "update":  # never analysed without a click (spec « Récupération des DCE »)
        if mailer is not None:
            from app.services.dce_retrieval import notify_update  # avoid an import cycle

            notify_update(db, fresh, mailer)
        return
    if queue is not None:
        from app.services.dce_analysis import request_analysis  # avoid an import cycle

        request_analysis(db, fresh, queue, user_id=fresh.uploaded_by, automatic=True)


def _finish(
    db: Session,
    version_id: uuid.UUID,
    status: str,
    error: str | None,
    skipped: list[dict[str, Any]],
) -> None:
    version = db.get(DceVersion, version_id, populate_existing=True)
    if version is None:
        db.commit()
        return
    version.status, version.error, version.skipped = status, error, skipped
    job_status = {"ready": "done", "processing": "pending"}.get(status, "error")
    set_job_status(db, JOB_KIND, version_id, job_status, error)
    db.commit()


# ---------- differences between versions (CA4) --------------------------------------------


def _key(path: str) -> str:
    return normalize(path)


def compute_diff(db: Session, version: DceVersion) -> tuple[dict[str, Any] | None, str | None]:
    previous = db.scalars(
        select(DceVersion)
        .where(
            DceVersion.bid_id == version.bid_id,
            DceVersion.version < version.version,
            DceVersion.status == "ready",
        )
        .order_by(DceVersion.version.desc())
    ).first()
    if previous is None:
        return None, None

    def files_of(v: DceVersion) -> dict[str, tuple[str, str]]:
        rows = db.scalars(select(DceFile).where(DceFile.dce_version_id == v.id))
        return {_key(f.path): (f.path, f.sha256) for f in rows}

    old, new = files_of(previous), files_of(version)
    old_hashes = {sha for _, sha in old.values()}
    new_hashes = {sha for _, sha in new.values()}
    modified = sorted(new[k][0] for k in new.keys() & old.keys() if new[k][1] != old[k][1])
    added = sorted(p for k, (p, sha) in new.items() if k not in old and sha not in old_hashes)
    removed = sorted(p for k, (p, sha) in old.items() if k not in new and sha not in new_hashes)
    diff = {
        "previous_version": previous.version,
        "added": added,
        "removed": removed,
        "modified": modified,
    }

    def part(n: int, one: str, many: str, names: list[str]) -> str:
        label = one if n == 1 else many
        return f"{n} {label}" + (
            f" ({', '.join(n_.rsplit('/', 1)[-1] for n_ in names[:5])})" if names else ""
        )

    if not (added or removed or modified):
        summary = f"Aucun changement de fichier par rapport à la version {previous.version}."
    else:
        summary = (
            f"Par rapport à la version {previous.version} : "
            + ", ".join(
                [
                    part(len(modified), "fichier modifié", "fichiers modifiés", modified),
                    part(len(added), "ajouté", "ajoutés", added),
                    part(len(removed), "supprimé", "supprimés", removed),
                ]
            )
            + "."
        )
    return diff, summary
