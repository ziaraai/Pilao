import logging
import uuid
from datetime import UTC, date, datetime
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import AuditLog, ComplianceDocument, File, Job, Organization, User
from app.documents.extract import ExtractionError
from app.domain import vault as rules
from app.domain.filetypes import JPEG, PDF, PNG
from app.schemas.vault import ComplianceDocOut, ConfirmIn, MissingOut, SummaryOut
from app.services import files as files_svc
from app.services.document_reading import DocumentReader
from app.storage.antivirus import VirusScanner
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.vault")
JOB_KIND = "read_compliance_document"
ALLOWED_MIMES = frozenset({PDF.mime, PNG.mime, JPEG.mime})


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- presentation ------------------------------------------------------------------


def _status(doc: ComplianceDocument, org: Organization, today: date) -> rules.StatusInfo:
    return rules.effective_status(
        confirmed=doc.confirmed_at is not None,
        siren_ok=rules.siren_matches(doc.siren_on_document, org.siren),
        valid_until=doc.valid_until,
        today=today,
    )


def to_out(doc: ComplianceDocument, org: Organization, today: date) -> ComplianceDocOut:
    siren_ok = rules.siren_matches(doc.siren_on_document, org.siren)
    info = _status(doc, org, today)
    alerts: list[str] = []
    if not siren_ok:
        alerts.append(
            f"Le SIREN du document ({doc.siren_on_document}) ne correspond pas à celui de "
            f"votre entreprise ({org.siren})."
        )
    if info.status == "expired":
        alerts.append("Ce document est expiré : il ne sera pas inclus dans vos exports.")
    elif info.status == "expiring":
        alerts.append(f"Ce document expire dans {info.days_left} jour(s).")
    out = ComplianceDocOut.model_validate(doc)
    return out.model_copy(
        update={"status": info.status, "days_left": info.days_left, "alerts": alerts}
    )


# ---------- commands ----------------------------------------------------------------------


def create_document(
    db: Session,
    org: Organization,
    user: User,
    fileobj: BinaryIO,
    filename: str | None,
    kind_hint: str | None,
    storage: ObjectStorage,
    scanner: VirusScanner,
    queue: JobQueue,
) -> ComplianceDocument:
    record = files_svc.upload_file(
        db, org, user, fileobj, filename, storage, scanner, allowed_mimes=ALLOWED_MIMES
    )
    doc = ComplianceDocument(file_id=record.id, kind=kind_hint or "other")
    db.add(doc)
    db.flush()
    _enqueue_reading(db, doc, queue)
    return doc


def _enqueue_reading(db: Session, doc: ComplianceDocument, queue: JobQueue) -> None:
    db.add(Job(kind=JOB_KIND, ref_id=doc.id, org_id=doc.org_id, status="pending"))
    doc.reading_status, doc.reading_error = "pending", None
    db.commit()
    try:
        queue.enqueue_read_compliance_document(doc.id)
    except Exception:
        logger.exception("could not enqueue reading of %s", doc.id)
        doc.reading_status = "error"
        doc.reading_error = "Lecture automatique indisponible : saisissez les dates à la main."
        db.commit()


def reread(db: Session, doc: ComplianceDocument, queue: JobQueue) -> None:
    if doc.reading_status in ("pending", "reading"):
        raise ApiError(409, "already_running", "La lecture est déjà en cours.")
    if doc.confirmed_at is not None:
        raise ApiError(409, "already_confirmed", "Ce document est déjà confirmé.")
    _enqueue_reading(db, doc, queue)


def confirm(
    db: Session, org: Organization, user: User, doc: ComplianceDocument, data: ConfirmIn
) -> ComplianceDocument:
    if (data.kind, data.valid_until) != (doc.kind, doc.valid_until):
        # The suggested rule no longer explains the date: it is now the user's own entry.
        doc.validity_rule = "written" if data.valid_until else None
    doc.kind, doc.issuer = data.kind, data.issuer
    doc.siren_on_document = data.siren_on_document
    doc.issued_at, doc.valid_until = data.issued_at, data.valid_until
    doc.confirmed_by, doc.confirmed_at = user.id, _now()
    doc.status = _status(doc, org, rules.paris_today()).status
    db.add(
        AuditLog(
            user_id=user.id,
            action="confirm",
            entity="compliance_document",
            entity_id=doc.id,
            meta={"kind": doc.kind, "valid_until": str(doc.valid_until), "status": doc.status},
        )
    )
    db.commit()
    return doc


def delete_document(
    db: Session, user: User, doc: ComplianceDocument, storage: ObjectStorage
) -> None:
    record = db.get_one(File, doc.file_id)
    files_svc.delete_file(db, user, record, storage)  # cascades to the document row


# ---------- background job ----------------------------------------------------------------


def _set_job(db: Session, doc_id: uuid.UUID, status: str, error: str | None = None) -> None:
    job = db.scalars(
        select(Job)
        .where(Job.kind == JOB_KIND, Job.ref_id == doc_id)
        .order_by(Job.created_at.desc())
    ).first()
    if job is None:
        return
    job.status, job.error = status, error
    if status == "running":
        job.started_at = _now()
    if status in ("done", "error"):
        job.finished_at, job.progress = _now(), (100 if status == "done" else job.progress)


def run_read_document(
    db: Session, doc_id: uuid.UUID, storage: ObjectStorage, reader: DocumentReader
) -> None:
    """Pre-fill the vault entry from the document. The user must still confirm (CA2)."""
    doc = db.get(ComplianceDocument, doc_id)
    if doc is None:
        return
    scope_session(db, doc.org_id)
    org = db.get_one(Organization, doc.org_id)
    record = db.get_one(File, doc.file_id)
    doc.reading_status, doc.reading_error = "reading", None
    _set_job(db, doc_id, "running")
    db.commit()

    try:
        fileobj = storage.get(record.storage_key)
        try:
            result = reader.read(db, org, fileobj, record.mime)
        finally:
            fileobj.close()
    except llm.LlmProviderError:
        _fail(db, doc_id, "Lecture interrompue, nouvelle tentative en cours.", permanent=False)
        raise  # lets RQ retry
    except (llm.LlmError, ExtractionError) as exc:  # permanent: retrying cannot help
        _fail(db, doc_id, _user_message(exc), permanent=True)
        return
    except Exception:
        _fail(db, doc_id, "Lecture interrompue, nouvelle tentative en cours.", permanent=False)
        raise

    # The session does not expire on commit: reload (and lock) the row, so that a confirmation
    # made by the user while the model was reading is seen, and a deleted document is skipped.
    fresh = db.get(ComplianceDocument, doc_id, populate_existing=True, with_for_update=True)
    if fresh is None:
        return
    doc = fresh
    data = result.data
    doc.extracted = {
        **result.raw,
        "_meta": {"model": result.model, "prompt_version": result.prompt_version},
    }
    doc.holder_name, doc.verification_code = data.holder_name, data.verification_code
    if doc.confirmed_at is None:  # never overwrite what the user has already confirmed
        if doc.kind == "other":  # keep a kind the user chose when uploading
            doc.kind = data.kind
        valid_until, rule = rules.derive_valid_until(doc.kind, data.issued_at, data.valid_until)
        if data.valid_until is not None and data.validity_rule is not None:
            rule = data.validity_rule  # e.g. the model applied the Kbis 3-month rule itself
        doc.issuer, doc.siren_on_document = data.issuer, data.siren_on_document
        doc.issued_at, doc.valid_until = data.issued_at, valid_until
        doc.validity_rule = rule
    doc.reading_status = "done"
    _set_job(db, doc_id, "done")
    db.commit()


def _user_message(exc: Exception) -> str:
    if isinstance(exc, llm.LlmNotConfigured):
        return "Lecture automatique non configurée : saisissez les informations à la main."
    if isinstance(exc, llm.LlmBudgetExceeded):
        return "Budget IA mensuel atteint : saisissez les informations à la main."
    if isinstance(exc, llm.LlmInvalidOutput):
        return (
            "Le document n'a pas pu être lu automatiquement : saisissez les informations à la main."
        )
    return str(exc)


def _fail(db: Session, doc_id: uuid.UUID, message: str, permanent: bool) -> None:
    db.rollback()
    doc = db.get_one(ComplianceDocument, doc_id)
    doc.reading_status, doc.reading_error = "error", message
    _set_job(db, doc_id, "error", message if permanent else "transient failure")
    db.commit()


# ---------- queries -----------------------------------------------------------------------


def summary(db: Session, org: Organization, today: date) -> SummaryOut:
    docs = [to_out(d, org, today) for d in db.scalars(select(ComplianceDocument))]
    counts = {s: 0 for s in rules.STATUSES}
    for d in docs:
        counts[d.status] += 1
    attention = sorted(
        (d for d in docs if d.status != "valid"),
        key=lambda d: (d.days_left is None, d.days_left if d.days_left is not None else 0),
    )
    have = {d.kind for d in docs if rules.is_usable(d.status)}
    missing = [
        MissingOut(label=label, kinds=list(kinds))
        for label, kinds in rules.RECOMMENDED
        if not have & set(kinds)
    ]
    return SummaryOut(counts=counts, attention=attention, missing=missing)


def usable_documents(db: Session, org: Organization, today: date) -> list[ComplianceDocument]:
    """Documents that may go into an export: confirmed and in date (US-5.2)."""
    return [
        d
        for d in db.scalars(select(ComplianceDocument))
        if rules.is_usable(_status(d, org, today).status)
    ]


def refresh_stored_statuses(db: Session, today: date) -> int:
    """Daily job (P3-05): re-derive the stored status of every confirmed document.

    Runs on an unscoped session. Returns the number of rows whose status changed.
    """
    changed = 0
    orgs = {o.id: o for o in db.scalars(select(Organization))}
    for doc in db.scalars(
        select(ComplianceDocument).where(ComplianceDocument.confirmed_at.is_not(None))
    ):
        status = _status(doc, orgs[doc.org_id], today).status
        if status != doc.status:
            doc.status = status
            changed += 1
    db.commit()
    return changed
