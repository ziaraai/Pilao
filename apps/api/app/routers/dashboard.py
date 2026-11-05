from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.core.deps import CurrentAuth, ScopedDb
from app.db.models import Bid, Tender, TenderMatch
from app.routers.tenders import match_out
from app.schemas.bids import BidOut
from app.schemas.tenders import TenderMatchOut
from app.schemas.vault import ComplianceDocOut
from app.services import vault as vault_svc
from app.services.documents import today_paris

router = APIRouter(tags=["dashboard"])
OPEN = ("to_review", "in_progress")
STATUSES = ("to_review", "in_progress", "submitted", "won", "lost", "dropped")


class ResultsOut(BaseModel):
    won: int
    lost: int
    submitted: int
    success_rate: float | None  # won / (won + lost), None before the first result


class DashboardOut(BaseModel):
    new_tenders: int  # matched these last 7 days, still open
    best_tenders: list[TenderMatchOut]
    bids_by_status: dict[str, list[BidOut]]
    deadlines_soon: list[BidOut]  # open bids due within 10 days
    documents_to_renew: list[ComplianceDocOut]
    results: ResultsOut


@router.get("/dashboard")
def dashboard(ctx: CurrentAuth, db: ScopedDb) -> DashboardOut:
    """US-5.3: new notices, bids by status, near deadlines, attestations, success rate."""
    now = datetime.now(UTC)
    open_notice = or_(Tender.deadline_at.is_(None), Tender.deadline_at > now)
    fresh = db.execute(
        select(TenderMatch, Tender)
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(
            TenderMatch.status == "new",
            TenderMatch.created_at >= now - timedelta(days=7),
            open_notice,
        )
        .order_by(TenderMatch.score.desc().nulls_last(), Tender.deadline_at.asc().nulls_last())
    ).all()
    bids = db.scalars(
        select(Bid).order_by(Bid.deadline_at.asc().nulls_last(), Bid.created_at)
    ).all()
    by_status: dict[str, list[BidOut]] = {s: [] for s in STATUSES}
    for bid in bids:
        by_status[bid.status].append(BidOut.model_validate(bid))
    soon = [
        BidOut.model_validate(b)
        for b in bids
        if b.status in OPEN and b.deadline_at and now <= b.deadline_at <= now + timedelta(days=10)
    ]
    summary = vault_svc.summary(db, ctx.org, today_paris())
    won, lost = len(by_status["won"]), len(by_status["lost"])
    return DashboardOut(
        new_tenders=len(fresh),
        best_tenders=[match_out(m, t) for m, t in fresh[:3]],
        bids_by_status=by_status,
        deadlines_soon=soon,
        documents_to_renew=[d for d in summary.attention if d.status != "pending_review"],
        results=ResultsOut(
            won=won,
            lost=lost,
            submitted=len(by_status["submitted"]),
            success_rate=round(won / (won + lost), 2) if won + lost else None,
        ),
    )
