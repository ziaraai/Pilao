"""The DCE e-mail address (ADR-055): each company has ``dce+CODE@pilao.pro``; the e-mails read
from that mailbox bring the DCE's pieces to the right dossier, or wait « À classer »."""

import hashlib
import io
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import runtime
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.tenancy import scope_session, unscope_session
from app.db.models import AuditLog, Bid, DceVersion, File, InboundMail, Organization, User
from app.domain import inbound_mail as rules
from app.integrations.imap_mailbox import Mailbox, MailboxError
from app.modules import has_module
from app.platform_settings import DCE_MAIL, DCE_MAIL_PASSWORD
from app.services import dce as dce_svc
from app.services import files as files_svc
from app.storage.antivirus import VirusScanner
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.dce_mail")
OPEN_STATUSES = ("to_review", "in_progress")
_REASONS = {
    "unsupported_type": dce_svc.UNREADABLE,
    "infected_file": "virus détecté",
    "empty_file": "fichier vide",
    "file_too_large": "fichier trop volumineux",
    "too_large_for_scan": "fichier trop volumineux",
    "quota_exceeded": "espace de stockage plein",
}
NOTICES_KEPT_DAYS = 90
POLL_LOCK = 0x5043_4D41  # pg advisory lock: one pass at a time over the mailbox


# ---------- the address --------------------------------------------------------------------


def _parts() -> tuple[str, str]:
    local, _, domain = get_settings().dce_mail_address.partition("@")
    return local.lower(), domain.lower()


def active() -> bool:
    """The mailbox is switched on and has its password: the address can be given out."""
    return bool(runtime.effective(DCE_MAIL)) and bool(runtime.secret(DCE_MAIL_PASSWORD))


def address(db: Session, org: Organization) -> str:
    """The company's address, its code given at the first reading and kept for good."""
    if org.dce_mail_code is None:
        for _ in range(5):
            org.dce_mail_code = rules.new_code()
            try:
                db.commit()
                break
            except IntegrityError:  # the same code drawn twice: draw again
                db.rollback()
        else:
            raise ApiError(503, "no_code", "Adresse indisponible, réessayez.")
    local, domain = _parts()
    return f"{local}+{org.dce_mail_code}@{domain}"


# ---------- reception (worker) -------------------------------------------------------------


def _mb(size: int) -> int:
    return size // (1024 * 1024)


def _org_of_sender(db: Session, parsed: rules.ParsedMail) -> Organization | None:
    """Without a code (the plain address): one of a company's users, whose domain our mail
    server checked. Such an e-mail is never filed by itself."""
    server = get_settings().dce_mail_server_name or None
    if not rules.authenticated(parsed.sender, parsed.auth_results, server):
        return None
    user = db.scalars(select(User).where(User.email == parsed.sender)).first()
    return db.get(Organization, user.org_id) if user is not None else None


def _author(db: Session, sender: str) -> User | None:
    """Who deposits: the sender when it is one of the company's users, else its first admin."""
    user = db.scalars(select(User).where(User.email == sender)).first()
    if user is not None:
        return user
    return db.scalars(
        select(User).order_by((User.role == "org_admin").desc(), User.created_at)
    ).first()


def _store(
    db: Session,
    org: Organization,
    author: User,
    attachments: list[rules.Attachment],
    storage: ObjectStorage,
    scanner: VirusScanner,
) -> tuple[list[File], list[dict[str, Any]]]:
    stored: list[File] = []
    skipped: list[dict[str, Any]] = []
    limit = get_settings().max_dce_upload_bytes
    try:
        for i, att in enumerate(attachments):
            if i >= dce_svc.MAX_FILES_PER_DEPOSIT:
                skipped.append({"path": att.filename, "reason": "trop de pièces", "deposit": True})
                continue
            try:
                stored.append(
                    files_svc.upload_file(
                        db,
                        org,
                        author,
                        io.BytesIO(att.data),
                        att.filename,
                        storage,
                        scanner,
                        allowed_mimes=dce_svc.DEPOSIT_MIMES,
                        max_bytes=limit,
                    )
                )
            except ApiError as exc:
                if exc.code not in _REASONS:
                    raise  # the antivirus is down: the e-mail stays in the mailbox
                skipped.append(
                    {"path": att.filename, "reason": _REASONS[exc.code], "deposit": True}
                )
    except Exception:
        db.rollback()
        _delete(db, author, [f.id for f in stored], storage)
        raise
    return stored, skipped


def _delete(db: Session, user: User | None, ids: list[uuid.UUID], storage: ObjectStorage) -> None:
    for file_id in ids:
        record = db.get(File, file_id)
        if record is not None:
            files_svc.delete_file(db, user, record, storage)


def _match(db: Session, parsed: rules.ParsedMail) -> Bid | None:
    bids = db.scalars(select(Bid).where(Bid.status.in_(OPEN_STATUSES))).all()
    refs = [rules.DossierRef(b.id, b.reference, b.title, b.buyer_name) for b in bids]
    found = rules.match_dossier(parsed.subject, parsed.text, refs)
    return next((b for b in bids if b.id == found), None)


def _has_dce(db: Session, bid: Bid) -> bool:
    found = db.scalar(select(DceVersion.id).where(DceVersion.bid_id == bid.id).limit(1))
    return found is not None


def receive(
    db: Session,
    raw: bytes,
    storage: ObjectStorage,
    scanner: VirusScanner,
    queue: JobQueue,
    *,
    oversized: bool = False,
) -> InboundMail | None:
    """One e-mail read from the mailbox (``db`` unscoped: the worker's). None: nobody's
    (unknown code, a stranger, a company without the « Réponse » module or suspended); the
    caller then deletes it. Raises when it must be read again (antivirus down)."""
    parsed = rules.parse(raw)
    local, domain = _parts()
    code = rules.code_from(parsed.recipients, local, domain)
    if code is not None:
        org = db.scalars(select(Organization).where(Organization.dce_mail_code == code)).first()
    else:
        org = _org_of_sender(db, parsed)
    if org is None or org.suspended_at is not None or not has_module(org, "reponse"):
        logger.info("DCE e-mail dropped (code %s, no company)", code)
        return None
    scope_session(db, org.id)
    message_id = (parsed.message_id or hashlib.sha256(raw).hexdigest())[:500]
    known = db.scalars(select(InboundMail).where(InboundMail.message_id == message_id)).first()
    if known is not None:
        return known
    author = _author(db, parsed.sender)
    if author is None:
        return None

    stored: list[File] = []
    skipped: list[dict[str, Any]] = []
    if not oversized:  # else only its header was read: the company downloads the DCE itself
        stored, skipped = _store(db, org, author, parsed.attachments, storage, scanner)
    bid = _match(db, parsed)
    mail = InboundMail(
        org_id=org.id,
        message_id=message_id,
        sender=parsed.sender[:320],
        subject=parsed.subject[:500],
        received_at=datetime.now(UTC),
        kind="dce" if stored else "notice",
        status="to_sort",
        file_ids=[f.id for f in stored],
        attachment_names=[f.filename for f in stored],
        skipped=skipped,
        links=parsed.links[:20],
        suggested_bid_id=bid.id if bid else None,
    )
    if oversized:
        mail.note = f"message trop volumineux (plus de {_mb(get_settings().dce_mail_max_bytes)} Mo)"
    elif not stored and not parsed.links:
        mail.status, mail.note = "ignored", "aucune pièce lisible ni lien"
    elif not stored and bid is not None and rules.is_update_notice(parsed.subject, parsed.text):
        mail.status, mail.bid_id = "filed", bid.id  # shown on the dossier
    db.add(mail)
    try:
        db.commit()
    except IntegrityError:  # read twice at the same time: the other one keeps it
        db.rollback()
        _delete(db, author, [f.id for f in stored], storage)
        return db.scalars(select(InboundMail).where(InboundMail.message_id == message_id)).first()

    # the address with the code, a dossier without DCE yet: deposited, analysis on the go
    if stored and code is not None and bid is not None and not _has_dce(db, bid):
        mail.status, mail.bid_id, mail.file_ids = "filed", bid.id, []
        try:
            dce_svc.version_from_files(db, org, author, bid, stored, skipped, queue)
        except ApiError:
            db.rollback()  # a deposit is being read: it waits « À classer »
    return mail


@dataclass
class PollResult:
    read: int = 0
    kept: int = 0  # filed or « À classer »
    dropped: int = 0  # nobody's
    failed: int = 0  # left in the mailbox, flagged
    stopped: str | None = None  # why the pass stopped early (antivirus down…)


def poll(
    sessions: Callable[[], Session],
    mailbox: Mailbox,
    storage: ObjectStorage,
    scanner: VirusScanner,
    queue: JobQueue,
) -> PollResult:
    """Every 2 minutes: each e-mail is read, then deleted from the mailbox. One that cannot be
    read is flagged and left there (never read again by itself); when the antivirus is down,
    the pass stops and everything is read again next time."""
    result = PollResult()
    limit = get_settings().dce_mail_max_bytes
    with sessions() as lock:
        if not lock.execute(text("select pg_try_advisory_lock(:k)"), {"k": POLL_LOCK}).scalar():
            result.stopped = "relève déjà en cours"
            return result
        try:
            for waiting in mailbox.waiting():
                if waiting.flagged:
                    continue
                result.read += 1
                try:
                    oversized = waiting.size > limit
                    raw = (
                        mailbox.fetch_header(waiting.uid)
                        if oversized
                        else mailbox.fetch(waiting.uid)
                    )
                    with sessions() as db:
                        mail = receive(db, raw, storage, scanner, queue, oversized=oversized)
                except ApiError as exc:
                    if exc.code == "scan_unavailable":
                        result.stopped = "antivirus indisponible"
                        break
                    logger.exception("DCE e-mail %s not read", waiting.uid)
                    mailbox.flag(waiting.uid)
                    result.failed += 1
                    continue
                except MailboxError as exc:
                    result.stopped = str(exc)
                    break
                except Exception:
                    logger.exception("DCE e-mail %s not read", waiting.uid)
                    mailbox.flag(waiting.uid)
                    result.failed += 1
                    continue
                if mail is None:
                    result.dropped += 1
                else:
                    result.kept += 1
                mailbox.delete(waiting.uid)
        finally:
            lock.execute(text("select pg_advisory_unlock(:k)"), {"k": POLL_LOCK})
            lock.commit()
    return result


# ---------- the company's side -------------------------------------------------------------


def inbox(db: Session) -> list[InboundMail]:
    return list(
        db.scalars(
            select(InboundMail)
            .where(InboundMail.status == "to_sort")
            .order_by(InboundMail.received_at.desc())
        )
    )


def notices(db: Session, bid: Bid) -> list[InboundMail]:
    since = datetime.now(UTC) - timedelta(days=NOTICES_KEPT_DAYS)
    return list(
        db.scalars(
            select(InboundMail)
            .where(
                InboundMail.bid_id == bid.id,
                InboundMail.kind == "notice",
                InboundMail.status == "filed",
                InboundMail.received_at >= since,
            )
            .order_by(InboundMail.received_at.desc())
        )
    )


def _waiting(db: Session, mail_id: uuid.UUID) -> InboundMail:
    mail = db.get(InboundMail, mail_id)
    if mail is None or mail.status != "to_sort":
        raise ApiError(404, "not_found", "Message introuvable.")
    return mail


def _pieces(db: Session, mail: InboundMail) -> list[File]:
    files = [f for f in (db.get(File, i) for i in mail.file_ids) if f is not None]
    if not files:
        raise ApiError(409, "no_pieces", "Les pièces de ce message ne sont plus disponibles.")
    return files


def file_mail(
    db: Session,
    org: Organization,
    user: User,
    mail_id: uuid.UUID,
    bid: Bid,
    mode: Literal["new", "add"],
    queue: JobQueue,
) -> DceVersion:
    """« Ranger dans… »: a new version of the dossier's DCE, or forgotten pieces of the
    current one. The analysis waits for the go, as for a deposit by hand."""
    mail = _waiting(db, mail_id)
    if mail.kind != "dce":
        raise ApiError(409, "no_pieces", "Ce message n'a pas de pièce jointe à ranger.")
    files = _pieces(db, mail)
    mail.status, mail.bid_id, mail.file_ids = "filed", bid.id, []  # committed with the version
    db.add(AuditLog(user_id=user.id, action="file_mail", entity="bid", entity_id=bid.id))
    if mode == "add":
        return dce_svc.add_stored_files(db, bid, files, mail.skipped, queue)
    return dce_svc.version_from_files(db, org, user, bid, files, mail.skipped, queue)


def bid_from_mail(
    db: Session, org: Organization, user: User, mail_id: uuid.UUID, queue: JobQueue
) -> Bid:
    """« Créer le dossier »: named after the subject; the pieces become its DCE, or the link
    received becomes its consultation's link."""
    mail = _waiting(db, mail_id)
    files = _pieces(db, mail) if mail.kind == "dce" else []
    bid = Bid(
        title=rules.title_from_subject(mail.subject),
        owner_user_id=user.id,
        status="to_review",
        dce_url=mail.links[0] if mail.kind == "notice" and mail.links else None,
    )
    db.add(bid)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="create", entity="bid", entity_id=bid.id))
    mail.status, mail.bid_id, mail.file_ids = "filed", bid.id, []
    if files:
        dce_svc.version_from_files(db, org, user, bid, files, mail.skipped, queue)
    else:
        db.commit()
    return bid


def ignore(db: Session, user: User, mail_id: uuid.UUID, storage: ObjectStorage) -> None:
    mail = _waiting(db, mail_id)
    _delete(db, user, list(mail.file_ids), storage)
    mail.status, mail.file_ids = "ignored", []
    db.commit()


def dismiss_notice(db: Session, mail_id: uuid.UUID) -> None:
    mail = db.get(InboundMail, mail_id)
    if mail is None or mail.kind != "notice" or mail.status != "filed":
        raise ApiError(404, "not_found", "Avis introuvable.")
    mail.status = "ignored"
    db.commit()


# ---------- retention (scheduler) ----------------------------------------------------------


def purge(db: Session, storage: ObjectStorage, now: datetime | None = None) -> int:
    """« À classer » waits ``dce_mail_retention_days``, then its pieces are removed; the trace
    of an e-mail (its subject, against reading it twice) is kept 180 days. ``db`` unscoped."""
    now = now or datetime.now(UTC)
    stale = now - timedelta(days=get_settings().dce_mail_retention_days)
    waiting = db.execute(
        select(InboundMail.id, InboundMail.org_id).where(
            InboundMail.status == "to_sort", InboundMail.received_at < stale
        )
    ).all()
    for mail_id, org_id in waiting:
        scope_session(db, org_id)
        mail = db.get_one(InboundMail, mail_id)
        _delete(db, None, list(mail.file_ids), storage)
        mail.status, mail.file_ids, mail.note = "ignored", [], "non classé à temps"
        db.commit()
    unscope_session(db)  # the old traces of every company
    db.execute(
        delete(InboundMail).where(
            InboundMail.received_at < now - timedelta(days=180),
            InboundMail.status != "to_sort",
        )
    )
    db.commit()
    return len(waiting)
