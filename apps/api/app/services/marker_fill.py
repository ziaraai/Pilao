"""« Ce qu'il manque » (ADR-048): complete a missing item with the AI, one sentence at a time.

The model sees only the unit that holds the marker (the sentence, the list line or the table
cell) and the company's data; it returns that unit, which the server splices back, so the
rest of the chapter cannot change. A unit is kept only when the marker is gone and it holds
no number or name absent from the company's data (the same guard as the drafting). A chapter
edited while the completion ran is left alone.
"""

import json
import logging
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    Bid,
    Job,
    MarkerFill,
    Memoir,
    MemoirSection,
    Organization,
    User,
)
from app.domain.memoir_checks import (
    check_chapter,
    flag_dicts,
    flags_after_edit,
    force_title,
    numbers_in,
)
from app.domain.missing import markers, splice, units
from app.schemas.drafting import MarkerFillOut
from app.services import credits
from app.services.jobs import set_job_status
from app.services.memoir_drafting import _tag_safe, company_data
from app.services.memoir_editing import add_revision, mark_matrix_stale
from app.services.missing import BUSY_MESSAGE, latest_memoir, memoir_busy, missing_for_bid
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.marker_fill")

JOB_FILL = "fill_marker"
FILL_PROMPT = "completion_repere"
PROVIDER_DOWN = "Service d'IA indisponible : réessayez."
QUEUE_DOWN = "File d'attente indisponible : réessayez."
FAILED = "La complétion n'a pas abouti : réessayez."
INTERRUPTED = "La complétion a été interrompue : réessayez."
# Past the queue's timeout (600 s): a completion still « en cours » is dead (worker killed)
STALE_AFTER = timedelta(minutes=15)


def close_stale(db: Session, fill: MarkerFill) -> None:
    """A completion left for dead: failed, its credits given back (caller commits)."""
    fill.status, fill.error = "error", INTERRUPTED
    set_job_status(db, JOB_FILL, fill.id, "error", INTERRUPTED)


def _accepted(sentence: str, unit_text: str, key: str, company: str) -> bool:
    """The model's sentence is kept only when it fills the marker and invents nothing: the
    marker is gone, every other marker of the unit is still there, and every number (even
    1 to 10, which the drafting's guard tolerates) and every name comes from the company's
    data or from the unit itself."""
    if any(m.key == key for m in markers(sentence)):
        return False
    others = Counter(m.key for m in markers(unit_text) if m.key != key)
    if Counter(m.key for m in markers(sentence) if m.key != key) != others:
        return False  # another missing item silently dropped (or added)
    context = company + "\n" + unit_text
    if not numbers_in(sentence) <= numbers_in(context):
        return False
    return not any(f.type in ("number", "name") for f in check_chapter(sentence, context, [], 0))


def start_fill(db: Session, user: User, bid: Bid, key: str, queue: JobQueue) -> MarkerFill:
    """Ask for the completion of ``key`` in every chapter holding it (in the background)."""
    credits.lock_org(db, bid.org_id)  # a second click waits here, then finds the first one
    memoir = latest_memoir(db, bid)
    if memoir is not None and memoir_busy(db, memoir):
        raise ApiError(409, "memoir_busy", BUSY_MESSAGE)
    item = next((i for i in missing_for_bid(db, bid).items if i.key == key and i.sections), None)
    if memoir is None or item is None:
        raise ApiError(404, "unknown_marker", "Cette information n'est plus à compléter.")
    running = db.scalars(
        select(MarkerFill).where(
            MarkerFill.memoir_id == memoir.id,
            MarkerFill.key == key,
            MarkerFill.status.in_(("pending", "running")),
        )
    ).first()
    if running is not None:
        if running.updated_at >= datetime.now(UTC) - STALE_AFTER:
            return running  # already on its way: never charged twice
        close_stale(db, running)  # left for dead: refunded, and a new one can start
    fill = MarkerFill(
        org_id=bid.org_id,
        memoir_id=memoir.id,
        key=key,
        marker_text=item.text,
        kind=item.kind,
        status="pending",
        created_by=user.id,
    )
    db.add(fill)
    db.flush()
    db.add(Job(kind=JOB_FILL, ref_id=fill.id, org_id=bid.org_id, status="pending"))
    db.add(
        AuditLog(
            user_id=user.id,
            action="fill_marker",
            entity="memoir",
            entity_id=memoir.id,
            meta={"key": key},
        )
    )
    credits.charge(
        db,
        db.get_one(Organization, bid.org_id),
        "marker_fill",
        user_id=user.id,
        bid_id=bid.id,
        ref_id=fill.id,
    )
    db.commit()
    try:
        queue.enqueue_fill_marker(fill.id)
    except Exception:
        logger.exception("could not enqueue marker fill %s", fill.id)
        _fail(db, fill, QUEUE_DOWN)
    return fill


def _fail(db: Session, fill: MarkerFill, message: str) -> None:
    fill.status, fill.error = "error", message
    set_job_status(db, JOB_FILL, fill.id, "error", message)  # gives the credits back
    db.commit()


def run_fill_marker(db: Session, fill_id: uuid.UUID) -> None:
    fill = db.get(MarkerFill, fill_id)
    if fill is None or fill.status not in ("pending", "running"):
        return
    scope_session(db, fill.org_id)
    memoir = db.get_one(Memoir, fill.memoir_id)
    bid = db.get_one(Bid, memoir.bid_id)
    org = db.get_one(Organization, fill.org_id)
    fill.status = "running"
    set_job_status(db, JOB_FILL, fill.id, "running")
    db.commit()

    prompt = load_prompt(FILL_PROMPT)
    sections = db.scalars(
        select(MemoirSection)
        .where(MemoirSection.memoir_id == memoir.id, MemoirSection.status == "ready")
        .order_by(MemoirSection.position)
    ).all()
    try:
        company = json.dumps(company_data(db, org), ensure_ascii=False, indent=1)
        for section in sections:
            content, revision = section.content_md or "", section.revision
            body, model = content, None
            for unit in reversed(units(content, fill.key)):
                system, user = prompt.render(
                    tender_title=_tag_safe(bid.title),
                    marker=_tag_safe(fill.marker_text),
                    sentence=_tag_safe(unit.text),
                    company_structured_json=company,
                )
                result = llm.complete(
                    db,
                    org_id=org.id,
                    task="marker_fill",
                    bid_id=bid.id,
                    prompt_version=prompt.version,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_model=MarkerFillOut,
                    max_tokens=600,
                )
                sentence = result.data.sentence.strip()
                if not result.data.filled or not _accepted(sentence, unit.text, fill.key, company):
                    continue  # a fact absent from the company's data: never written
                body, model = splice(body, unit, sentence), result.model
            if body == content:
                continue
            locked = db.get(MemoirSection, section.id, with_for_update=True, populate_existing=True)
            if locked is None or locked.revision != revision or locked.content_md != content:
                db.commit()  # edited meanwhile: the user's text wins
                continue
            locked.content_md = force_title(body, locked.title)
            locked.flags = flag_dicts(
                flags_after_edit(locked.content_md, locked.flags, locked.word_budget)
            )
            add_revision(
                db,
                locked,
                "generated",
                None,
                instruction=f"Complété : {fill.marker_text}",
                model=model,
                prompt_version=prompt.version,
            )
            mark_matrix_stale(memoir)
            fill.sections_filled += 1
            db.commit()
    except llm.LlmProviderError:
        db.rollback()
        _fail(db, db.get_one(MarkerFill, fill_id), PROVIDER_DOWN)
        return
    except llm.LlmError as exc:
        db.rollback()
        _fail(db, db.get_one(MarkerFill, fill_id), str(exc))
        return
    except Exception:
        logger.exception("marker fill %s failed", fill_id)
        db.rollback()
        _fail(db, db.get_one(MarkerFill, fill_id), FAILED)
        return
    fill.outcome = "filled" if fill.sections_filled else "not_enough"
    fill.status = "done"
    set_job_status(db, JOB_FILL, fill.id, "done")
    db.commit()
