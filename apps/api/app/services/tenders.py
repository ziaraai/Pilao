"""The watch: notices in, matches per company, AI score, actions (US-2.1 to US-2.3).

Notices arrive in the normalized :class:`TenderIn` shape whatever their source (the BOAMP
and TED importers convert to it). Each new or changed notice is pre-filtered for every
company (deterministic, free), and only the notices that pass are scored by the model,
from that company's own profile.
"""

import logging
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.core.email import Email, Mailer, send_quietly
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    Bid,
    CompanyProfile,
    Notification,
    Tender,
    TenderMatch,
    User,
)
from app.domain.tender_filter import (
    CompanyFilter,
    TenderFacts,
    prefilter,
    same_buyer,
    similar_titles,
)
from app.domain.trades import TRADES
from app.schemas.tenders import TenderIn, TenderScoreOut
from app.services.documents import paris
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.tenders")
SCORE_PROMPT = "scoring_annonce"
SCORE_BATCH = 100  # per company and per run: a full batch schedules the next one
CLAIM_TIMEOUT = timedelta(minutes=15)  # a killed job's claims are taken back after this
OPEN_WINDOW = timedelta(days=120)  # a notice without deadline is "open" this long
CORRECTED_FIELDS = (
    "title",
    "description",
    "deadline_at",
    "estimated_amount_cents",
    "documents_url",
    "procedure",
    "cpv_codes",
    "departments",
    "lots",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _tag_safe(text: str) -> str:
    return re.sub(r"</?\s*(company|tender)", "‹", text, flags=re.IGNORECASE)


def facts(t: Tender) -> TenderFacts:
    return TenderFacts(
        title=t.title,
        description=t.description,
        lot_titles=[str(lot.get("title", "")) for lot in t.lots],
        cpv_codes=t.cpv_codes,
        departments=t.departments,
        estimated_amount_cents=t.estimated_amount_cents,
        deadline_at=t.deadline_at,
    )


def company_filter(profile: CompanyProfile | None) -> CompanyFilter:
    if profile is None:
        return CompanyFilter()
    return CompanyFilter(
        cpv_codes=profile.cpv_codes,
        keywords_include=profile.keywords_include,
        keywords_exclude=profile.keywords_exclude,
        departments=profile.departments,
        min_amount_cents=profile.min_amount_cents,
        max_amount_cents=profile.max_amount_cents,
    )


# ---------- ingestion (US-2.1) ---------------------------------------------------------


@dataclass
class IngestReport:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    corrected: int = 0
    awards: int = 0
    duplicates: int = 0
    to_match: list[uuid.UUID] = field(default_factory=list)


def _values(item: TenderIn) -> dict[str, Any]:
    return {
        "notice_type": item.notice_type,
        "title": item.title,
        "description": item.description,
        "buyer_name": item.buyer_name,
        "buyer_siret": item.buyer_siret,
        "procedure": item.procedure,
        "contract_nature": item.contract_nature,
        "cpv_codes": item.cpv_codes,
        "departments": item.departments,
        "nuts_codes": item.nuts_codes,
        "estimated_amount_cents": (
            None if item.estimated_amount_eur is None else round(item.estimated_amount_eur * 100)
        ),
        "published_at": item.published_at,
        "deadline_at": item.deadline_at,
        "notice_url": item.notice_url,
        "documents_url": item.documents_url,
        "lots": [lot.model_dump() for lot in item.lots],
        "raw": item.raw,
    }


def _duplicate_of(db: Session, tender: Tender) -> uuid.UUID | None:
    """The same contract already received from the other source (US-2.1 CA1)."""
    if tender.deadline_at is None:
        return None
    day = timedelta(hours=36)
    for other in db.scalars(
        select(Tender).where(
            Tender.source != tender.source,
            Tender.duplicate_of.is_(None),
            Tender.notice_type == "contract_notice",
            Tender.deadline_at.between(tender.deadline_at - day, tender.deadline_at + day),
        )
    ):
        if same_buyer(other.buyer_name, tender.buyer_name) and similar_titles(
            other.title, tender.title
        ):
            return other.id
    return None


def ingest(db: Session, items: Sequence[TenderIn], mailer: Mailer) -> IngestReport:
    """Upsert notices (unscoped session: notices are global). Commits."""
    report = IngestReport()
    for item in items:
        if item.notice_type == "correction" and item.corrects:
            target = db.scalar(
                select(Tender).where(
                    Tender.source == item.source, Tender.source_id == item.corrects
                )
            )
            if target is not None:
                if _apply_correction(db, target, item, mailer):
                    report.corrected += 1
                    report.to_match.append(target.id)
                else:
                    report.unchanged += 1
                continue
        values = _values(item)
        existing = db.scalar(
            select(Tender).where(Tender.source == item.source, Tender.source_id == item.source_id)
        )
        if existing is not None:
            changed = {k for k, v in values.items() if getattr(existing, k) != v and k != "raw"}
            if not changed:
                report.unchanged += 1
                continue
            for key, value in values.items():
                setattr(existing, key, value)
            report.updated += 1
            if existing.notice_type == "contract_notice" and existing.duplicate_of is None:
                report.to_match.append(existing.id)
            continue
        tender = Tender(id=uuid.uuid4(), source=item.source, source_id=item.source_id, **values)
        if tender.notice_type == "contract_notice":
            tender.duplicate_of = _duplicate_of(db, tender)
        db.add(tender)
        db.flush()
        report.created += 1
        if tender.notice_type == "award":
            report.awards += 1  # stored for V2 (DECP, competitors), never in the watch (CA3)
        elif tender.duplicate_of is not None:
            report.duplicates += 1
        elif tender.notice_type == "contract_notice":
            report.to_match.append(tender.id)
    db.commit()
    return report


def _fmt(key: str, value: Any) -> str:
    if value is None or value == [] or value == "":
        return "—"
    if key == "deadline_at" and isinstance(value, datetime):
        return paris(value) or "—"
    if key == "estimated_amount_cents" and isinstance(value, int):
        return f"{round(value / 100):,} € HT".replace(",", " ")
    if isinstance(value, list):
        return ", ".join(str(x.get("title", x)) if isinstance(x, dict) else str(x) for x in value)
    return str(value)[:300]


LABELS = {
    "title": "objet",
    "description": "description",
    "deadline_at": "date limite",
    "estimated_amount_cents": "montant estimé",
    "documents_url": "lien du DCE",
    "procedure": "procédure",
    "cpv_codes": "codes CPV",
    "departments": "lieu",
    "lots": "lots",
}


def _apply_correction(db: Session, target: Tender, item: TenderIn, mailer: Mailer) -> bool:
    """A correction updates the notice it modifies and warns the companies following it."""
    values = _values(item)
    changes: dict[str, tuple[Any, Any]] = {}
    for key in CORRECTED_FIELDS:
        new = values[key]
        if new in (None, [], "") or new == getattr(target, key):
            continue
        changes[key] = (getattr(target, key), new)
        setattr(target, key, new)
    if not changes:
        return False
    target.corrections = [
        *target.corrections,
        {
            "source_id": item.source_id,
            "received_at": _now().isoformat(),
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "changes": {LABELS[k]: [_fmt(k, a), _fmt(k, b)] for k, (a, b) in changes.items()},
        },
    ]
    tracked = db.scalars(
        select(TenderMatch).where(
            TenderMatch.tender_id == target.id, TenderMatch.status == "tracked"
        )
    ).all()
    for match in tracked:
        if "deadline_at" in changes and match.bid_id is not None:
            bid = db.get(Bid, match.bid_id)
            old = changes["deadline_at"][0]
            if bid is not None and bid.deadline_at in (None, old):
                bid.deadline_at = target.deadline_at  # the user's own date is kept
        notify(
            db,
            mailer,
            match.org_id,
            "correction",
            f"{target.id}:{item.source_id}",
            f"Avis rectificatif : {target.title[:120]}",
            "Un avis rectificatif modifie un marché que vous suivez :\n\n"
            + "\n".join(
                f"- {LABELS[k]} : {_fmt(k, a)} → {_fmt(k, b)}" for k, (a, b) in changes.items()
            )
            + "\n\nVérifiez votre dossier dans Pilao.",
        )
    db.flush()
    return True


def notify(
    db: Session, mailer: Mailer, org_id: uuid.UUID, kind: str, key: str, subject: str, body: str
) -> bool:
    """E-mail every verified user of the organization, once per (kind, key)."""
    if db.scalar(
        select(Notification.id).where(
            Notification.org_id == org_id, Notification.kind == kind, Notification.key == key
        )
    ):
        return False
    users = db.scalars(
        select(User).where(User.org_id == org_id, User.email_verified_at.is_not(None))
    ).all()
    sent = sum(send_quietly(mailer, Email(to=u.email, subject=subject, body=body)) for u in users)
    if users and not sent:
        return False  # the mail server is down: not recorded, so retried next hour
    db.add(Notification(org_id=org_id, kind=kind, key=key, recipients=sent))
    db.flush()
    return True


# ---------- matching (US-2.2 CA1) ------------------------------------------------------


def _open_tenders(now: datetime) -> Any:
    return select(Tender).where(
        Tender.notice_type == "contract_notice",
        Tender.duplicate_of.is_(None),
        or_(
            Tender.deadline_at > now,
            Tender.deadline_at.is_(None) & (Tender.published_at > now - OPEN_WINDOW),
        ),
    )


def match_tenders(
    db: Session, tender_ids: Sequence[uuid.UUID], queue: JobQueue, now: datetime | None = None
) -> int:
    """Pre-filter new or changed notices for every company (unscoped). Returns new matches."""
    now = now or _now()
    tenders = db.scalars(_open_tenders(now).where(Tender.id.in_(list(tender_ids)))).all()
    if not tenders:
        return 0
    created = 0
    to_score: set[uuid.UUID] = set()
    for profile in db.scalars(select(CompanyProfile)):
        rules = company_filter(profile)
        if not rules.watches_something:
            continue
        known = set(
            db.scalars(
                select(TenderMatch.tender_id).where(
                    TenderMatch.org_id == profile.org_id,
                    TenderMatch.tender_id.in_([t.id for t in tenders]),
                )
            )
        )
        for tender in tenders:
            if tender.id in known:
                continue
            decision = prefilter(rules, facts(tender), now)
            if decision.passed:
                db.add(
                    TenderMatch(
                        org_id=profile.org_id, tender_id=tender.id, reasons=decision.reasons
                    )
                )
                created += 1
                to_score.add(profile.org_id)
    db.commit()
    for org_id in to_score:
        _enqueue_score(queue, org_id)
    return created


def rematch_org(
    db: Session, org_id: uuid.UUID, queue: JobQueue, now: datetime | None = None
) -> None:
    """US-1.2 CA4: after a profile change, filter and score the open notices again."""
    now = now or _now()
    scope_session(db, org_id)
    rules = company_filter(db.scalar(select(CompanyProfile)))
    matches = {m.tender_id: m for m in db.scalars(select(TenderMatch))}
    for tender in db.scalars(_open_tenders(now)):
        decision = prefilter(rules, facts(tender), now)
        match = matches.get(tender.id)
        if match is None:
            if decision.passed:
                db.add(TenderMatch(org_id=org_id, tender_id=tender.id, reasons=decision.reasons))
        elif match.status == "new":
            if not decision.passed:
                db.delete(match)  # no longer in the company's scope
            else:  # the score depended on the old profile
                match.reasons = decision.reasons
                match.score = match.explanation = match.score_error = match.scored_at = None
                match.relevant_lots = []
    db.commit()
    _enqueue_score(queue, org_id)


def _enqueue_score(queue: JobQueue, org_id: uuid.UUID) -> None:
    try:
        queue.enqueue_score_tenders(org_id)
    except Exception:  # the next import or profile change schedules it again
        logger.exception("could not enqueue the scoring of %s", org_id)


# ---------- AI score (US-2.2 CA2) -----------------------------------------------------


def _eur(cents: int | None) -> str:
    return "non précisé" if cents is None else f"{round(cents / 100):,}".replace(",", " ")


def _unscored(now: datetime) -> Any:
    """Matches waiting for a score; a claim older than CLAIM_TIMEOUT is abandoned."""
    return (
        TenderMatch.status == "new",
        TenderMatch.score.is_(None),
        TenderMatch.score_error.is_(None),
        or_(TenderMatch.scored_at.is_(None), TenderMatch.scored_at < now - CLAIM_TIMEOUT),
    )


def score_org(
    db: Session, org_id: uuid.UUID, queue: JobQueue | None = None, now: datetime | None = None
) -> int:
    """Score this company's unscored matches; returns how many were scored.

    Each match is claimed (``scored_at`` set, no score yet) before the model is called, so
    two jobs running at once never pay twice for the same notice. A full batch schedules the
    next one.
    """
    now = now or _now()
    scope_session(db, org_id)
    profile = db.scalar(select(CompanyProfile))
    if profile is None:
        return 0
    pending = db.execute(
        select(TenderMatch, Tender)
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(
            *_unscored(now),
            or_(Tender.deadline_at.is_(None), Tender.deadline_at > now),
        )
        .order_by(Tender.published_at.desc().nulls_last())
        .limit(SCORE_BATCH)
    ).all()
    prompt = load_prompt(SCORE_PROMPT)
    company = {
        "trades": ", ".join(TRADES[t].label for t in profile.trades if t in TRADES)
        or "non précisés",
        "keywords_include": ", ".join(profile.keywords_include) or "aucun",
        "keywords_exclude": ", ".join(profile.keywords_exclude) or "aucun",
        "departments": ", ".join(profile.departments) or "toute la France",
        "min_amount": _eur(profile.min_amount_cents),
        "max_amount": _eur(profile.max_amount_cents),
    }
    scored = 0
    for match, tender in pending:
        claimed = db.execute(
            update(TenderMatch)
            .where(TenderMatch.id == match.id, *_unscored(now))
            .values(scored_at=now)
        )
        db.commit()
        if claimed.rowcount != 1:  # type: ignore[attr-defined]
            continue  # another job is scoring it
        system, user = prompt.render(
            **company,
            title=_tag_safe(tender.title),
            description=_tag_safe((tender.description or "non précisée")[:4000]),
            buyer_name=_tag_safe(tender.buyer_name or "non précisé"),
            cpv_codes=", ".join(tender.cpv_codes) or "non précisés",
            tender_departments=", ".join(tender.departments) or "non précisé",
            estimated_amount=(
                "non précisé"
                if tender.estimated_amount_cents is None
                else f"{_eur(tender.estimated_amount_cents)} € HT"
            ),
            lots=_tag_safe(
                "; ".join(f"{lot.get('number') or '?'} : {lot.get('title')}" for lot in tender.lots)
                or "aucun"
            ),
        )
        try:
            result = llm.complete(
                db,
                org_id=org_id,
                task="tender_scoring",
                prompt_version=prompt.version,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_model=TenderScoreOut,
                max_tokens=400,
            )
        except (llm.LlmNotConfigured, llm.LlmBudgetExceeded):
            _release(db, match.id)
            return scored  # the list still shows the pre-filtered notices, without a score
        except llm.LlmProviderError:
            _release(db, match.id)
            raise  # transient: the job is retried, scored matches are kept
        except llm.LlmError as exc:
            match.score_error = str(exc)[:300]
            db.commit()
            continue
        match.score, match.explanation = result.data.score, result.data.explanation
        match.relevant_lots = result.data.relevant_lots
        match.model, match.prompt_version, match.scored_at = result.model, prompt.version, now
        db.commit()
        scored += 1
    if len(pending) == SCORE_BATCH and queue is not None:
        _enqueue_score(queue, org_id)  # more are waiting
    return scored


def _release(db: Session, match_id: uuid.UUID) -> None:
    db.rollback()
    db.execute(update(TenderMatch).where(TenderMatch.id == match_id).values(scored_at=None))
    db.commit()


# ---------- actions (US-2.3) ----------------------------------------------------------


def get_match(db: Session, tender_id: uuid.UUID) -> tuple[TenderMatch, Tender]:
    row = db.execute(
        select(TenderMatch, Tender)
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(TenderMatch.tender_id == tender_id)
    ).first()
    if row is None:
        raise ApiError(404, "not_found", "Annonce introuvable.")
    return row[0], row[1]


def track(db: Session, user: User, tender_id: uuid.UUID) -> Bid:
    """Follow a notice: it becomes a bid « à étudier » (idempotent)."""
    match, tender = get_match(db, tender_id)
    if match.bid_id is not None and (bid := db.get(Bid, match.bid_id)) is not None:
        match.status = "tracked"
        db.commit()
        return bid
    bid = Bid(
        title=tender.title[:300],
        buyer_name=(tender.buyer_name or None) and tender.buyer_name[:300],
        deadline_at=tender.deadline_at,
        tender_id=tender.id,
        owner_user_id=user.id,
        status="to_review",
    )
    db.add(bid)
    db.flush()
    match.status, match.bid_id, match.dismiss_reason = "tracked", bid.id, None
    db.add(AuditLog(user_id=user.id, action="track", entity="tender", entity_id=tender.id))
    db.commit()
    return bid


def dismiss(db: Session, user: User, tender_id: uuid.UUID, reason: str) -> TenderMatch:
    match, tender = get_match(db, tender_id)
    if match.status == "tracked":
        raise ApiError(409, "tender_tracked", "Ce marché est suivi : supprimez d'abord le dossier.")
    match.status, match.dismiss_reason = "dismissed", reason
    db.add(
        AuditLog(
            user_id=user.id,
            action="dismiss",
            entity="tender",
            entity_id=tender.id,
            meta={"reason": reason},
        )
    )
    db.commit()
    return match


def restore(db: Session, user: User, tender_id: uuid.UUID) -> TenderMatch:
    match, tender = get_match(db, tender_id)
    if match.status == "dismissed":
        match.status, match.dismiss_reason = "new", None
        db.add(AuditLog(user_id=user.id, action="restore", entity="tender", entity_id=tender.id))
        db.commit()
    return match


def release_matches(db: Session, bid_id: uuid.UUID) -> None:
    """A deleted bid gives its notice back to the list (the caller commits)."""
    for match in db.scalars(select(TenderMatch).where(TenderMatch.bid_id == bid_id)):
        match.status, match.bid_id = "new", None
