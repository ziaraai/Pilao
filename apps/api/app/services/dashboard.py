"""Dashboard data (US-5.3): the facts the rules of ``domain/dashboard.py`` need.

Runs on the company's scoped session: every query below sees this company's rows only.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.db.models import (
    Bid,
    DceAnalysis,
    DceVersion,
    KnowledgeDocument,
    Memoir,
    MemoirSection,
    Organization,
)
from app.domain import dashboard as rules
from app.exports.dc_forms import PROOF_LABELS
from app.services import profile as profile_svc
from app.services import vault as vault_svc
from app.services.documents import today_paris


@dataclass(frozen=True)
class Board:
    actions: list[rules.Action]
    getting_started: list[rules.Step]  # empty once every step is done
    bids: list[tuple[rules.BidFacts, rules.Progress]]  # in progress and awaiting a result
    all_bids: list[Bid]


def _latest(db: Session, model: type[DceVersion] | type[DceAnalysis]) -> dict[uuid.UUID, str]:
    """Status of the latest row of ``model`` for each bid."""
    order = model.version.desc() if model is DceVersion else model.created_at.desc()
    rows = db.execute(
        select(model.bid_id, model.status)
        .ext(distinct_on(model.bid_id))
        .order_by(model.bid_id, order)
    ).all()
    return {bid_id: status for bid_id, status in rows}


def _chapters(db: Session) -> dict[uuid.UUID, tuple[int, int, int]]:
    """(drafted, drafting, total) chapters of the latest memoir of each bid."""
    latest = dict(
        db.execute(
            select(Memoir.id, Memoir.bid_id)
            .ext(distinct_on(Memoir.bid_id))
            .order_by(Memoir.bid_id, Memoir.version.desc())
        ).all()
    )
    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if latest:
        for memoir_id, status, n in db.execute(
            select(MemoirSection.memoir_id, MemoirSection.status, func.count())
            .where(MemoirSection.memoir_id.in_(latest))
            .group_by(MemoirSection.memoir_id, MemoirSection.status)
        ).all():
            counts[memoir_id][status] = n
    return {
        bid_id: (
            counts[memoir_id]["ready"],
            counts[memoir_id]["generating"],
            sum(counts[memoir_id].values()),
        )
        for memoir_id, bid_id in latest.items()
    }


def build(db: Session, org: Organization) -> Board:
    now, today = datetime.now(UTC), today_paris()
    bids = db.scalars(
        select(Bid).order_by(Bid.deadline_at.asc().nulls_last(), Bid.created_at)
    ).all()
    dce, analysis, chapters = _latest(db, DceVersion), _latest(db, DceAnalysis), _chapters(db)
    facts = [
        rules.BidFacts(
            id=b.id,
            title=b.title,
            buyer_name=b.buyer_name,
            deadline_at=b.deadline_at,
            status=b.status,
            dce=dce.get(b.id),
            analysis=analysis.get(b.id),
            chapters=chapters.get(b.id),
        )
        for b in bids
    ]
    vault = vault_svc.summary(db, org, today)
    docs = [
        rules.DocFacts(PROOF_LABELS.get(d.kind, d.kind), d.status, d.valid_until)
        for d in vault.attention
    ]
    profile = profile_svc.get_or_create_profile(db, org)
    pct = profile_svc.compute_completeness(db, org, profile).pct
    knowledge = db.scalar(select(func.count()).select_from(KnowledgeDocument)) or 0
    steps = rules.getting_started(pct, [m.label for m in vault.missing], knowledge, len(bids))
    following = sorted(  # in progress by deadline, then the offers awaiting their result
        (f for f in facts if f.status in (*rules.OPEN, "submitted")),
        key=lambda f: f.status == "submitted",
    )
    return Board(
        actions=rules.actions(facts, docs, today, now),
        getting_started=[] if all(s.done for s in steps) else steps,
        bids=[(f, rules.progress(f)) for f in following],
        all_bids=list(bids),
    )
