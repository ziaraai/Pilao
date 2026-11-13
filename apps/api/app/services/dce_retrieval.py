"""DCE retrieval (spec « Récupération des DCE »): on request from a dossier, by the robot on PLACE
and the Atexo platforms; the ZIP then follows the path of a deposit (``dce.create_version``).

A retrieval costs nothing; its version starts the analysis like a deposit (credits taken). An
update found by the daily watch is never analysed without a click (§ 1, decision 5).
"""

import logging
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import runtime
from app.core.config import get_settings
from app.core.email import Email, Mailer, send_quietly
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import AuditLog, Bid, DceFetch, DceVersion, Job, Organization, Tender, User
from app.domain.dce_sources import (
    PARIS,
    DceSource,
    PageFacts,
    recognize,
    watch_change,
    watch_state,
)
from app.integrations.atexo import MESSAGES, DceRobot, Identity, RobotError, RobotUnavailable
from app.integrations.robot_net import url_allowed
from app.platform_settings import DCE_ROBOT
from app.services.jobs import set_job_status
from app.storage.antivirus import VirusScanner
from app.storage.objects import ObjectStorage
from app.workers.host_gate import HostGate
from app.workers.queue import (
    DCE_JOB_TIMEOUT_SECONDS,
    FETCH_JOB_TIMEOUT_SECONDS,
    JobQueue,
    will_retry,
)

logger = logging.getLogger("pilao.dce_retrieval")

JOB_KIND = "fetch_dce"
MODES = ("identified", "anonymous")
ACTIVE = ("pending", "running")
REQUESTED = ("retrieval", "update")
STALE_AFTER = timedelta(seconds=2 * FETCH_JOB_TIMEOUT_SECONDS)
BUSY_RETRY_SECONDS = 60
INTERRUPTED = "La récupération a été interrompue. Réessayez."
BAD_LINK = "Collez un lien qui commence par https://"
NOT_AUTOMATIC = "Ce lien ne peut pas être récupéré automatiquement."
CHOICE_NEEDED = "Choisissez comment récupérer le DCE."
CONTACT_INCOMPLETE = "Indiquez le prénom, le nom et l'e-mail du contact."
RUNNING = "Une récupération est déjà en cours pour ce dossier."
BUSY = "Un dépôt est déjà en cours de traitement."
ROBOT_OFF = (
    "La récupération automatique est arrêtée pour le moment. Ouvrez la page du DCE et déposez "
    "le ZIP."
)
QUEUE_DOWN = "File d'attente indisponible. Réessayez plus tard."
# A Pilao or platform failure (« À surveiller »), not an expected refusal (spec § 4.5)
FAILURES = ("unreadable", "unavailable")


@dataclass(frozen=True)
class Contact:
    first_name: str | None
    last_name: str | None
    email: str | None


def robot_enabled() -> bool:
    return bool(runtime.effective(DCE_ROBOT))


def source_for(db: Session, bid: Bid) -> DceSource | None:
    """The link pasted in the dossier, else the notice's DCE link."""
    if bid.dce_url:
        return recognize(bid.dce_url)
    if bid.tender_id is not None:
        tender = db.get(Tender, bid.tender_id)
        if tender is not None:
            return recognize(tender.documents_url)
    return None


def set_link(db: Session, user: User, bid: Bid, url: str | None) -> Bid:
    if url is None or not url.strip():
        bid.dce_url = None
    else:
        src = recognize(url)
        if src is None:
            raise ApiError(422, "bad_link", BAD_LINK)
        bid.dce_url = src.url
    db.add(
        AuditLog(
            org_id=bid.org_id,
            user_id=user.id,
            action="update",
            entity="bid",
            entity_id=bid.id,
            meta={"fields": ["dce_url"]},
        )
    )
    db.commit()
    return bid


def settings_for(org: Organization) -> tuple[str | None, Contact]:
    contact = Contact(
        org.buyer_contact_first_name, org.buyer_contact_last_name, org.buyer_contact_email
    )
    return org.dce_retrieval_mode, contact


def _clean(value: str | None) -> str | None:
    return value.strip() or None if value else None


def _store_contact(org: Organization, contact: Contact) -> None:
    org.buyer_contact_first_name = _clean(contact.first_name)
    org.buyer_contact_last_name = _clean(contact.last_name)
    org.buyer_contact_email = _clean(contact.email)


def save_settings(
    db: Session, user: User, org: Organization, mode: str | None, contact: Contact
) -> None:
    if mode is not None and mode not in MODES:
        raise ApiError(422, "bad_mode", CHOICE_NEEDED)
    org.dce_retrieval_mode = mode
    _store_contact(org, contact)
    db.add(
        AuditLog(
            org_id=org.id,
            user_id=user.id,
            action="update",
            entity="organization",
            entity_id=org.id,
            meta={"fields": ["dce_retrieval"]},
        )
    )
    db.commit()


def identity_for(org: Organization) -> Identity | None:
    """What the robot gives the platform on the company's behalf; ``None`` without a contact."""
    first, last, email = (
        org.buyer_contact_first_name,
        org.buyer_contact_last_name,
        org.buyer_contact_email,
    )
    if not (first and last and email):
        return None
    return Identity(first, last, email, org.name, org.siren, org.siret)


def latest_fetch(db: Session, bid_id: uuid.UUID) -> DceFetch | None:
    """The latest retrieval or update of the dossier (not the daily checks)."""
    return db.scalars(
        select(DceFetch)
        .where(DceFetch.bid_id == bid_id, DceFetch.kind.in_(REQUESTED))
        .order_by(DceFetch.created_at.desc())
    ).first()


def last_success(db: Session, bid: Bid) -> DceFetch | None:
    """The latest retrieval or update that brought a version from the dossier's current link."""
    src = source_for(db, bid)
    if src is None:
        return None
    return db.scalars(
        select(DceFetch)
        .join(DceVersion, DceVersion.id == DceFetch.dce_version_id)
        .where(
            DceFetch.bid_id == bid.id,
            DceFetch.kind.in_(REQUESTED),
            DceFetch.status == "done",
            DceFetch.outcome == "ok",
            DceVersion.source_url == src.url,
        )
        .order_by(DceFetch.created_at.desc())
    ).first()


def _automatic(src: DceSource | None) -> DceSource:
    allow_private = get_settings().dce_robot_allow_private_hosts
    if src is None or not src.automatic or not url_allowed(src.url, allow_private, resolve=False):
        raise ApiError(422, "not_automatic", NOT_AUTOMATIC)
    return src


def _deposit_busy(db: Session, bid_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(DceVersion.id).where(
                DceVersion.bid_id == bid_id,
                DceVersion.status.in_(("pending", "processing")),
                DceVersion.updated_at
                > datetime.now(UTC) - timedelta(seconds=2 * DCE_JOB_TIMEOUT_SECONDS),
            )
        )
        is not None
    )


def _running(db: Session, bid_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(DceFetch.id).where(
                DceFetch.bid_id == bid_id,
                DceFetch.kind.in_(REQUESTED),
                DceFetch.status.in_(ACTIVE),
            )
        )
        is not None
    )


def create_fetch(
    db: Session,
    bid: Bid,
    src: DceSource,
    *,
    kind: str,
    mode: str,
    requested_by: uuid.UUID | None,
    queue: JobQueue,
) -> DceFetch:
    """A retrieval or update in the queue; 409 if one is already active (even in a race)."""
    fetch = DceFetch(
        id=uuid.uuid4(),
        org_id=bid.org_id,
        bid_id=bid.id,
        kind=kind,
        mode=mode,
        status="pending",
        site=src.site,
        requested_by=requested_by,
    )
    db.add(fetch)
    db.add(Job(kind=JOB_KIND, ref_id=fetch.id, org_id=bid.org_id, status="pending"))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_dce_fetches_one_active_per_bid" not in str(exc.orig):
            raise
        raise ApiError(409, "retrieval_running", RUNNING) from None
    try:
        queue.enqueue_fetch_dce(fetch.id)
    except Exception:
        logger.exception("could not enqueue DCE fetch %s", fetch.id)
        _close(db, fetch, "unavailable", QUEUE_DOWN)
    return fetch


def request_retrieval(
    db: Session,
    org: Organization,
    user: User,
    bid: Bid,
    *,
    mode: str | None,
    remember: bool,
    contact: Contact | None,
    queue: JobQueue,
) -> DceFetch:
    if not robot_enabled():
        raise ApiError(409, "robot_disabled", ROBOT_OFF)
    src = _automatic(source_for(db, bid))
    chosen = mode or org.dce_retrieval_mode
    if chosen not in MODES:
        raise ApiError(409, "retrieval_choice_needed", CHOICE_NEEDED)
    if contact is not None:
        _store_contact(org, contact)
    if chosen == "identified" and identity_for(org) is None:
        db.rollback()
        raise ApiError(422, "contact_incomplete", CONTACT_INCOMPLETE)
    if remember:
        org.dce_retrieval_mode = chosen
    if _running(db, bid.id):
        db.rollback()
        raise ApiError(409, "retrieval_running", RUNNING)
    if _deposit_busy(db, bid.id):
        db.rollback()
        raise ApiError(409, "dce_processing", BUSY)
    db.add(
        AuditLog(
            org_id=org.id,
            user_id=user.id,
            action="create",
            entity="dce_fetch",
            entity_id=bid.id,
            meta={"mode": chosen, "site": src.site, "remember": remember},
        )
    )
    return create_fetch(
        db, bid, src, kind="retrieval", mode=chosen, requested_by=user.id, queue=queue
    )


# ---------- the job -------------------------------------------------------------------------


def _close(
    db: Session, fetch: DceFetch, outcome: str, message: str | None, *, status: str = "error"
) -> None:
    fetch.status, fetch.outcome, fetch.message = status, outcome, message
    fetch.finished_at = datetime.now(UTC)
    job_status = "error" if status == "error" and outcome in FAILURES else "done"
    set_job_status(db, JOB_KIND, fetch.id, job_status, message if job_status == "error" else None)
    db.commit()


def _depositor(db: Session, fetch: DceFetch, bid: Bid) -> User | None:
    """The user who asked (for an update: the one of the retrieval), else the dossier's owner."""
    for user_id in (fetch.requested_by, bid.owner_user_id):
        if user_id is not None:
            user = db.get(User, user_id)
            if user is not None:
                return user
    return db.scalars(select(User).where(User.org_id == bid.org_id)).first()


def run_fetch(
    db: Session,
    fetch_id: uuid.UUID,
    robot: DceRobot,
    storage: ObjectStorage,
    scanner: VirusScanner,
    queue: JobQueue,
    gate: HostGate,
) -> None:
    from app.services import dce as dce_svc  # dce imports this module for its update mail

    fetch = db.get(DceFetch, fetch_id)
    if fetch is None or fetch.status not in ACTIVE:
        return  # the dossier was deleted, or the sweep closed it
    scope_session(db, fetch.org_id)  # the worker's session: this company's rows only
    bid = db.get_one(Bid, fetch.bid_id)
    src = source_for(db, bid)
    if src is None or not src.automatic:
        _close(db, fetch, "unreadable", MESSAGES["unreadable"])
        return
    if not robot_enabled():
        _close(db, fetch, "disabled", ROBOT_OFF)
        return
    if not gate.acquire(src.host):  # another job is on this site: later
        queue.enqueue_fetch_dce(fetch.id, delay_seconds=BUSY_RETRY_SECONDS)
        return
    try:
        gate.wait_gap(src.host)
        org = db.get_one(Organization, fetch.org_id)
        identity = identity_for(org) if fetch.mode == "identified" else None
        if fetch.mode == "identified" and identity is None:
            fetch.mode = "anonymous"  # the contact was removed since: never send a half form
        fetch.status = "running"
        set_job_status(db, JOB_KIND, fetch.id, "running")
        db.commit()
        with tempfile.TemporaryDirectory(prefix="pilao-dce-") as tmp:
            try:
                fetched = robot.fetch(src, identity, Path(tmp), get_settings().max_dce_upload_bytes)
            except RobotError as exc:
                _close(db, fetch, exc.outcome, exc.message)
                return
            except RobotUnavailable:
                if will_retry():
                    fetch.status = "pending"
                    set_job_status(db, JOB_KIND, fetch.id, "pending")
                    db.commit()
                    raise
                _close(db, fetch, "unavailable", MESSAGES["unavailable"])
                return
            live = db.get(Bid, fetch.bid_id, populate_existing=True)
            if live is None or db.get(DceFetch, fetch_id, populate_existing=True) is None:
                return  # the dossier was deleted while the robot worked
            depositor = _depositor(db, fetch, live)
            if depositor is None:
                _close(db, fetch, "unreadable", MESSAGES["unreadable"])
                return
            try:
                with fetched.path.open("rb") as zipped:
                    version = dce_svc.create_version(
                        db,
                        org,
                        depositor,
                        live,
                        [(zipped, fetched.filename)],
                        storage,
                        scanner,
                        queue,
                        origin="retrieval" if fetch.kind == "retrieval" else "update",
                        source_url=src.url,
                    )
            except ApiError as exc:
                db.rollback()
                fetch = db.get_one(DceFetch, fetch_id)
                _close(
                    db, fetch, "busy" if exc.code == "dce_processing" else "unreadable", exc.message
                )
                return
        fetch = db.get_one(DceFetch, fetch_id, populate_existing=True)
        fetch.dce_version_id, fetch.size_label = version.id, fetched.size_label
        live = db.get_one(Bid, fetch.bid_id)
        facts = PageFacts(fetched.size_label, fetched.deadline_at, False)
        live.dce_watch = watch_state(facts, datetime.now(UTC))
        _close(db, fetch, "ok", None, status="done")
    finally:
        gate.release(src.host)


# ---------- the update mail -----------------------------------------------------------------


def notify_update(db: Session, version: DceVersion, mailer: Mailer) -> None:
    """« Le DCE a changé », once the new version's differences are known (spec § 4.3)."""
    bid = db.get(Bid, version.bid_id)
    if bid is None:
        return
    recipient = None
    for user_id in (bid.owner_user_id, version.uploaded_by):
        if user_id is not None and (user := db.get(User, user_id)) is not None:
            recipient = user
            break
    if recipient is None:
        return
    src = recognize(version.source_url)
    site = f" sur {src.site}" if src else ""
    link = f"{get_settings().app_base_url}/dossiers/{bid.id}"
    body = (
        f"Bonjour,\n\nLe dossier de consultation de « {bid.title} » a changé{site}.\n\n"
        f"{version.diff_summary or 'Des pièces ont changé.'}\n\n"
        "Pilao a récupéré la nouvelle version. Vérifiez les différences et lancez son analyse "
        f"depuis le dossier :\n{link}\n\n— Pilao"
    )
    send_quietly(
        mailer, Email(to=recipient.email, subject=f"Le DCE de « {bid.title} » a changé", body=body)
    )


# ---------- the daily watch (spec § 4.3) ----------------------------------------------------

MAX_FAILURES = 3
WATCHED_STATUSES = ("to_review", "in_progress")


@dataclass(frozen=True)
class WatchReport:
    checked: int
    changed: int
    failed: int


def _watched(db: Session, now: datetime) -> list[Bid]:
    """Open dossiers of active companies with « Réponse » whose DCE the robot retrieved."""
    retrieved = (
        select(DceFetch.id)
        .where(
            DceFetch.bid_id == Bid.id,
            DceFetch.kind == "retrieval",
            DceFetch.status == "done",
            DceFetch.outcome == "ok",
        )
        .exists()
    )
    bids = db.scalars(
        select(Bid)
        .join(Organization, Organization.id == Bid.org_id)
        .where(
            Bid.status.in_(WATCHED_STATUSES),
            (Bid.deadline_at.is_(None)) | (Bid.deadline_at > now),
            Organization.suspended_at.is_(None),
            Organization.modules.contains(["reponse"]),
            retrieved,
        )
        .order_by(Bid.created_at)
    ).all()
    return [b for b in bids if not (b.dce_watch or {}).get("stopped")]


def _paris(value: datetime | None) -> str:
    return value.astimezone(PARIS).strftime("%d/%m %H:%M") if value else "non renseignée"


def _recipient(db: Session, bid: Bid, fallback: uuid.UUID | None) -> User | None:
    for user_id in (bid.owner_user_id, fallback):
        if user_id is not None and (user := db.get(User, user_id)) is not None:
            return user
    return None


def _deadline_mail(
    db: Session,
    bid: Bid,
    site: str,
    old: datetime | None,
    new: datetime,
    requester: uuid.UUID | None,
    mailer: Mailer,
) -> None:
    recipient = _recipient(db, bid, requester)
    if recipient is None:
        return
    link = f"{get_settings().app_base_url}/dossiers/{bid.id}"
    body = (
        f"Bonjour,\n\nLa date limite de « {bid.title} » a changé sur {site} : "
        f"{_paris(old)} → {_paris(new)} (heure de Paris).\n\n"
        f"La date du dossier a été mise à jour :\n{link}\n\n— Pilao"
    )
    send_quietly(
        mailer,
        Email(to=recipient.email, subject=f"La date limite de « {bid.title} » a changé", body=body),
    )


def _check_one(
    db: Session,
    bid: Bid,
    robot: DceRobot,
    queue: JobQueue,
    mailer: Mailer,
    gate: HostGate,
    now: datetime,
) -> str | None:
    """One check; returns ``changed``, ``unchanged``, ``failed`` or ``None`` (skipped)."""
    src = source_for(db, bid)
    success = last_success(db, bid)
    if src is None or not src.automatic or success is None:
        return None
    if not gate.acquire(src.host):
        return None  # a retrieval is on this site: tomorrow
    check = DceFetch(
        org_id=bid.org_id, bid_id=bid.id, kind="check", status="running", site=src.site
    )
    db.add(check)
    db.commit()
    previous = dict(bid.dce_watch or {})
    try:
        gate.wait_gap(src.host)
        facts = robot.inspect(src)
        if facts.closed:
            raise RobotError("closed")
    except (RobotError, RobotUnavailable) as exc:
        failures = int(previous.get("failures") or 0) + 1
        outcome = exc.outcome if isinstance(exc, RobotError) else "unavailable"
        message = exc.message if isinstance(exc, RobotError) else MESSAGES["unavailable"]
        bid.dce_watch = {**previous, "failures": failures, "stopped": failures >= MAX_FAILURES}
        check.status, check.outcome, check.message = "error", outcome, message
        check.finished_at = now
        db.commit()
        return "failed"
    finally:
        gate.release(src.host)
    change = watch_change(previous, facts)
    seen = previous.get("deadline_at")  # the date the platform showed last time
    old_deadline = datetime.fromisoformat(seen) if seen else bid.deadline_at
    if change.deadline_changed and change.new_deadline is not None:
        bid.deadline_at = change.new_deadline  # the platform is the authority
    # the size seen stays the old one until the update brings the new files
    known = PageFacts(
        (
            previous.get("size_label")
            if change.size_changed
            else (facts.size_label or previous.get("size_label"))
        ),
        facts.deadline_at
        or (
            datetime.fromisoformat(previous["deadline_at"]) if previous.get("deadline_at") else None
        ),
        False,
    )
    bid.dce_watch = watch_state(known, now)
    check.status = "done"
    check.outcome = "changed" if (change.size_changed or change.deadline_changed) else "unchanged"
    check.size_label, check.finished_at = facts.size_label, now
    db.commit()
    if change.deadline_changed and change.new_deadline is not None:
        _deadline_mail(
            db, bid, src.site, old_deadline, change.new_deadline, success.requested_by, mailer
        )
    if change.size_changed:
        org = db.get_one(Organization, bid.org_id)
        mode = success.mode or "anonymous"
        if mode == "identified" and identity_for(org) is None:
            mode = "anonymous"
        try:
            create_fetch(
                db,
                bid,
                src,
                kind="update",
                mode=mode,
                requested_by=success.requested_by,
                queue=queue,
            )
        except ApiError:
            pass  # a retrieval is already running: it brings the new files
    return check.outcome


def watch_dces(
    db: Session,
    robot: DceRobot,
    queue: JobQueue,
    mailer: Mailer,
    gate: HostGate,
    now: datetime,
) -> WatchReport:
    """Every morning: read each watched consultation's page and react to a change."""
    if not robot_enabled():
        return WatchReport(0, 0, 0)
    checked = changed = failed = 0
    for bid in _watched(db, now):
        try:
            outcome = _check_one(db, bid, robot, queue, mailer, gate, now)
        except Exception:
            db.rollback()
            logger.exception("DCE watch failed for dossier %s", bid.id)
            continue
        if outcome is None:
            continue
        checked += 1
        changed += outcome == "changed"
        failed += outcome == "failed"
    return WatchReport(checked, changed, failed)


# ---------- dead attempts -------------------------------------------------------------------


def close_stale(db: Session, now: datetime) -> int:
    """Attempts left « en cours » by a killed worker (lot 4 sweep); caller commits."""
    stale = db.scalars(
        select(DceFetch).where(
            DceFetch.status.in_(ACTIVE),
            DceFetch.kind.in_(REQUESTED),
            DceFetch.created_at < now - STALE_AFTER,
        )
    ).all()
    for fetch in stale:
        fetch.status, fetch.outcome, fetch.message = "error", "unavailable", INTERRUPTED
        fetch.finished_at = now
        set_job_status(db, JOB_KIND, fetch.id, "error", INTERRUPTED)
    return len(stale)
