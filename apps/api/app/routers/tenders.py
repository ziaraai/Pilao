import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.core.deps import CurrentAuth, ScopedDb
from app.db.models import Tender, TenderMatch
from app.domain.tender_filter import cpv_hits
from app.domain.trades import TRADES
from app.schemas.bids import BidOut
from app.schemas.tenders import DismissIn, TenderListOut, TenderMatchOut
from app.services import tenders as svc

router = APIRouter(prefix="/tenders", tags=["tenders"])
PARIS = ZoneInfo("Europe/Paris")


def match_out(match: TenderMatch, tender: Tender) -> TenderMatchOut:
    return TenderMatchOut(
        tender_id=tender.id,
        source=tender.source,
        title=tender.title,
        description=tender.description,
        buyer_name=tender.buyer_name,
        procedure=tender.procedure,
        contract_nature=tender.contract_nature,
        cpv_codes=tender.cpv_codes,
        departments=tender.departments,
        estimated_amount_cents=tender.estimated_amount_cents,
        published_at=tender.published_at,
        deadline_at=tender.deadline_at,
        notice_url=tender.notice_url,
        documents_url=tender.documents_url,
        lots=tender.lots,
        corrections=tender.corrections,
        status=match.status,
        score=match.score,
        explanation=match.explanation,
        relevant_lots=match.relevant_lots,
        reasons=match.reasons,
        score_error=match.score_error,
        dismiss_reason=match.dismiss_reason,
        bid_id=match.bid_id,
    )


@router.get("")
def list_tenders(
    db: ScopedDb,
    status: Literal["new", "tracked", "dismissed"] = "new",
    department: str | None = None,
    trade: str | None = None,
    procedure: str | None = None,
    min_score: Annotated[int | None, Query(ge=0, le=100)] = None,
    deadline_before: date | None = None,
    min_amount_cents: Annotated[int | None, Query(ge=0)] = None,
    max_amount_cents: Annotated[int | None, Query(ge=0)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    include_closed: bool = False,
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
) -> TenderListOut:
    """US-2.2: this company's notices, best score first then nearest deadline (CA3, CA4)."""
    now = datetime.now(UTC)
    base = (
        select(TenderMatch, Tender)
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(TenderMatch.status == status)
    )
    if not include_closed and status == "new":
        base = base.where(or_(Tender.deadline_at.is_(None), Tender.deadline_at > now))
    facets = db.execute(base.with_only_columns(Tender.departments, Tender.procedure)).all()
    query = base
    if department:
        query = query.where(Tender.departments.contains([department]))
    if procedure:
        query = query.where(Tender.procedure == procedure)
    if min_score is not None:
        query = query.where(TenderMatch.score >= min_score)
    if deadline_before is not None:
        end = datetime.combine(deadline_before + timedelta(days=1), time(), PARIS)
        query = query.where(Tender.deadline_at < end)
    if min_amount_cents is not None:
        query = query.where(Tender.estimated_amount_cents >= min_amount_cents)
    if max_amount_cents is not None:
        query = query.where(Tender.estimated_amount_cents <= max_amount_cents)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Tender.title.ilike(like), Tender.buyer_name.ilike(like)))
    rows = db.execute(
        query.order_by(
            TenderMatch.score.desc().nulls_last(),
            Tender.deadline_at.asc().nulls_last(),
            Tender.id,
        )
    ).all()
    if trade and trade in TRADES:  # a sector = the CPV codes of that trade
        codes = list(TRADES[trade].cpv_codes)
        rows = [r for r in rows if cpv_hits(codes, r[1].cpv_codes)]
    total = len(rows)
    start = (page - 1) * per_page
    return TenderListOut(
        items=[match_out(m, t) for m, t in rows[start : start + per_page]],
        total=total,
        departments=sorted({d for deps, _ in facets for d in deps}),
        procedures=sorted({p for _, p in facets if p}),
    )


@router.get("/{tender_id}")
def read_tender(tender_id: uuid.UUID, db: ScopedDb) -> TenderMatchOut:
    match, tender = svc.get_match(db, tender_id)
    return match_out(match, tender)


@router.post("/{tender_id}/track", status_code=201)
def track(tender_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb) -> BidOut:
    """US-2.3: follow the notice: it becomes a bid « à étudier »."""
    return BidOut.model_validate(svc.track(db, ctx.user, tender_id))


@router.post("/{tender_id}/dismiss")
def dismiss(
    tender_id: uuid.UUID, data: DismissIn, ctx: CurrentAuth, db: ScopedDb
) -> TenderMatchOut:
    svc.dismiss(db, ctx.user, tender_id, data.reason)
    return read_tender(tender_id, db)


@router.post("/{tender_id}/restore")
def restore(tender_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb) -> TenderMatchOut:
    svc.restore(db, ctx.user, tender_id)
    return read_tender(tender_id, db)
