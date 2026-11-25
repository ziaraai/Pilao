"""A consultation read from its documents (25/11).

Once the documents are processed, one model call reads them: who asks for the quote, where the
works are, how to reach the client, the client's reference, and which document holds the
quantities to price. The server keeps only the facts the cited page has
(``domain.consultation.check_facts``) and puts them in the dossier's empty fields, each with its
source; what the user typed is never replaced. The documents proposed as price files become
« DPGF »; when there is only one, its reading starts at once, paid by this reading's credit
(``PriceSheet.included``).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    Bid,
    ConsultationRead,
    DceFile,
    DcePage,
    DceVersion,
    Job,
    Organization,
    PriceSheet,
    User,
)
from app.domain.consultation import COLUMNS, ConsultationReadOut, check_facts
from app.services import credits, pricing
from app.services.dce_analysis import PRICE_KINDS
from app.services.jobs import set_job_status
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.consultation_read")

JOB_KIND = "read_consultation"
TASK = "price_read"  # the same model and the same credit as the reading of a price file
ACTION = "price_read"
PROMPT = "lecture_consultation"
STALE_AFTER = timedelta(minutes=15)  # past the queue's timeout (600 s): the reading is dead
MAX_CHARS = 60_000
FIRST_PAGES = 2  # the first pages of every document go first: the header is there
MAX_OUTPUT_TOKENS = 4_000

QUEUE_DOWN = "File d'attente indisponible : relancez la lecture."
PROVIDER_DOWN = "Service d'IA indisponible : relancez la lecture."
FAILED = "La lecture des documents n'a pas abouti : relancez-la ou remplissez la fiche."
INTERRUPTED = "La lecture des documents a été interrompue : relancez-la."
NO_TEXT = "Pilao n'a pas pu lire le texte des documents : remplissez la fiche à la main."
WAITING_CREDITS = (
    "Crédits épuisés : les documents seront lus dès que des crédits seront ajoutés, ou "
    "remplissez la fiche à la main."
)
NOT_CONSULTATION = "Seule une consultation se lit ainsi : un appel d'offres s'analyse."
NO_DCE = "Déposez d'abord les documents reçus."


def get_read(db: Session, bid: Bid) -> ConsultationRead | None:
    return db.scalar(select(ConsultationRead).where(ConsultationRead.bid_id == bid.id))


def _ready_version(db: Session, bid: Bid) -> DceVersion | None:
    return db.scalars(
        select(DceVersion)
        .where(DceVersion.bid_id == bid.id, DceVersion.status == "ready")
        .order_by(DceVersion.version.desc())
    ).first()


def close_stale(db: Session, read: ConsultationRead) -> None:
    """A reading left for dead: failed, its credit given back (caller commits)."""
    read.status, read.error = "error", INTERRUPTED
    set_job_status(db, JOB_KIND, read.id, "error", INTERRUPTED)


def request_read(
    db: Session, bid: Bid, queue: JobQueue, *, user_id: uuid.UUID | None, automatic: bool
) -> ConsultationRead:
    """Read the documents (1 credit). Without enough credits, the reading that starts by
    itself at the deposit waits (``waiting_credits``); one asked by the user is refused (402)."""
    if bid.kind != "consultation":
        raise ApiError(422, "not_consultation", NOT_CONSULTATION)
    credits.lock_org(db, bid.org_id)  # a second click waits here, then finds the first one
    if _ready_version(db, bid) is None:
        raise ApiError(409, "dce_not_ready", NO_DCE)
    read = get_read(db, bid)
    if read is not None and read.status == "reading":
        if read.updated_at >= datetime.now(UTC) - STALE_AFTER:
            return read  # already on its way: never charged twice
        close_stale(db, read)
    if read is None:
        read = ConsultationRead(org_id=bid.org_id, bid_id=bid.id)
        db.add(read)
    read.status, read.error, read.created_by = "reading", None, user_id
    read.updated_at = datetime.now(UTC)
    db.flush()
    job = Job(kind=JOB_KIND, ref_id=read.id, org_id=bid.org_id, status="pending")
    db.add(job)
    db.flush()  # the charge comes after the work exists: a failure gives back this charge only
    try:
        credits.charge(
            db,
            db.get_one(Organization, bid.org_id),
            ACTION,
            user_id=user_id,
            bid_id=bid.id,
            ref_id=read.id,
        )
    except ApiError as exc:
        if not automatic or exc.code != "credits_exhausted":
            raise
        db.delete(job)
        read.status, read.error = "waiting_credits", WAITING_CREDITS
        db.commit()
        return read
    if user_id is not None:
        db.add(
            AuditLog(
                user_id=user_id,
                action="read_consultation",
                entity="bid",
                entity_id=bid.id,
                meta={"automatic": automatic},
            )
        )
    db.commit()
    try:
        queue.enqueue_read_consultation(read.id)
    except Exception:
        logger.exception("could not enqueue consultation reading %s", read.id)
        _fail(db, read, QUEUE_DOWN)
    return read


def _fail(db: Session, read: ConsultationRead, message: str) -> None:
    read.status, read.error = "error", message
    set_job_status(db, JOB_KIND, read.id, "error", message)  # gives the credit back
    db.commit()


def _pages(db: Session, files: list[DceFile]) -> tuple[str, dict[tuple[str, int], str], bool]:
    """The pages sent: the first ones of every document, then the others, up to MAX_CHARS.
    Returns the text, the pages by (file, page), and whether some were left out."""
    by_file: dict[uuid.UUID, list[DcePage]] = {f.id: [] for f in files}
    for page in db.scalars(
        select(DcePage)
        .where(DcePage.dce_file_id.in_(list(by_file)))
        .order_by(DcePage.dce_file_id, DcePage.page)
    ):
        if page.text and page.text.strip():
            by_file[page.dce_file_id].append(page)
    paths = {f.id: f.path for f in files}
    order = [(f.id, p) for f in files for p in by_file[f.id][:FIRST_PAGES]]
    order += [(f.id, p) for f in files for p in by_file[f.id][FIRST_PAGES:]]
    sent: dict[tuple[str, int], str] = {}
    size, cut = 0, False
    for file_id, page in order:
        block = len(page.text) + len(paths[file_id]) + 12
        if size + block > MAX_CHARS:
            cut = True
            continue  # a shorter page further on may still fit
        size += block
        sent[(paths[file_id], page.page)] = page.text
    rank = {f.path: i for i, f in enumerate(files)}
    ordered = sorted(sent.items(), key=lambda kv: (rank[kv[0][0]], kv[0][1]))
    text = "\n".join(
        f"[{path.replace('<', '‹')} p.{number}]\n{body.replace('</pages', '‹/pages')}"
        for (path, number), body in ordered
    )
    return text, sent, cut


def _file_named(files: list[DceFile], name: str) -> DceFile | None:
    """The document a name given by the model stands for: its path, or its file name alone
    when no other document has it."""
    exact = [f for f in files if f.path == name]
    if exact:
        return exact[0]
    base = name.rsplit("/", 1)[-1].casefold()
    same = [f for f in files if f.path.rsplit("/", 1)[-1].casefold() == base]
    return same[0] if len(same) == 1 else None


def _apply_facts(bid: Bid, kept: dict[str, tuple[str, str, int]]) -> list[str]:
    """Put each fact read into the dossier where the field is empty or still holds what Pilao
    put there; never over what the user typed. Returns the facts written."""
    sources: dict[str, Any] = dict(bid.facts_sources or {})
    written = []
    for name, (value, file, page) in kept.items():
        column = COLUMNS[name]
        current = getattr(bid, column)
        if current and column not in sources:
            continue  # typed by the user
        setattr(bid, column, value)
        sources[column] = {"file": file, "page": page}
        written.append(name)
    bid.facts_sources = sources  # a new object: an in-place change of JSONB is not saved
    return written


def _mark_price_files(read_out: ConsultationReadOut, files: list[DceFile]) -> list[dict[str, Any]]:
    """The documents proposed as price files become « DPGF » (unless the user typed them)."""
    found: list[dict[str, Any]] = []
    for item in read_out.price_files:
        dce_file = _file_named(files, item.file)
        if dce_file is None or any(p["dce_file_id"] == str(dce_file.id) for p in found):
            continue
        if dce_file.detected_kind not in PRICE_KINDS and not dce_file.kind_confirmed:
            dce_file.detected_kind, dce_file.kind_source = "dpgf", "ai"
        if dce_file.detected_kind in PRICE_KINDS:
            found.append(
                {
                    "dce_file_id": str(dce_file.id),
                    "path": dce_file.path,
                    "reason": item.reason.strip()[:300],
                }
            )
    return found


def _start_price_reading(db: Session, read: ConsultationRead, bid: Bid, queue: JobQueue) -> None:
    """One price file not read yet, and readable: its reading starts at once."""
    files = [f for f in pricing.shown_price_files(db, bid) if pricing.readable(db, f)]
    if len(files) != 1 or read.created_by is None:
        return
    if db.scalar(select(PriceSheet.id).where(PriceSheet.dce_file_id == files[0].id)):
        return  # already read (or reading): the user decides to read it again
    user = db.get(User, read.created_by)
    if user is None:
        return
    try:
        pricing.start_read(db, user, bid, files[0].id, queue)
    except ApiError as exc:
        logger.info("price reading of consultation %s not started: %s", bid.id, exc.code)
        db.rollback()


def run_read_consultation(db: Session, read_id: uuid.UUID, queue: JobQueue) -> None:
    read = db.get(ConsultationRead, read_id)
    if read is None or read.status != "reading":
        return
    scope_session(db, read.org_id)
    set_job_status(db, JOB_KIND, read.id, "running")
    read.updated_at = datetime.now(UTC)
    db.commit()
    bid = db.get_one(Bid, read.bid_id)
    try:
        version = _ready_version(db, bid)
        files = (
            list(
                db.scalars(
                    select(DceFile)
                    .where(DceFile.dce_version_id == version.id)
                    .order_by(DceFile.path)
                )
            )
            if version is not None
            else []
        )
        text, sent, _ = _pages(db, files)
        if not sent:
            _fail(db, read, NO_TEXT)
            return
        prompt = load_prompt(PROMPT)
        listed = "\n".join(f"- {f.path.replace('<', '‹')}" for f in files)
        system, user_msg = prompt.render(files=listed.replace("</files", "‹/files"), pages=text)
        result = llm.complete(
            db,
            org_id=read.org_id,
            task=TASK,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            response_model=ConsultationReadOut,
            prompt_version=prompt.version,
            bid_id=bid.id,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
        kept = check_facts(result.data, sent)
        written = _apply_facts(bid, kept)
        read.found = sorted(kept)
        read.price_files = _mark_price_files(result.data, files)
        read.status, read.error = "ready", None
        set_job_status(db, JOB_KIND, read.id, "done")
        logger.info("consultation %s read: %d facts written", bid.id, len(written))
        db.commit()
    except llm.LlmProviderError:
        db.rollback()
        _fail(db, read, PROVIDER_DOWN)
        return
    except llm.LlmError:
        db.rollback()
        _fail(db, read, FAILED)
        return
    except Exception:
        logger.exception("consultation reading %s failed", read_id)
        db.rollback()
        _fail(db, read, FAILED)
        return
    _start_price_reading(db, read, bid, queue)
