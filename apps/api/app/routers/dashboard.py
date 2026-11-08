import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.core.deps import CurrentAuth, ScopedDb
from app.db.models import Tender, TenderMatch
from app.routers.tenders import match_out
from app.schemas.tenders import TenderMatchOut
from app.services import dashboard as svc
from app.services import feedback as feedback_svc

router = APIRouter(tags=["dashboard"])


class ActionOut(BaseModel):
    level: Literal["urgent", "soon", "todo"]
    title: str
    detail: str | None
    href: str
    button: str
    due: date | None


class StepOut(BaseModel):
    key: str
    title: str
    detail: str
    href: str
    done: bool


class BidProgressOut(BaseModel):
    id: uuid.UUID
    title: str
    buyer_name: str | None
    deadline_at: datetime | None
    status: str
    done: list[Literal["dce", "analysis", "memoir", "submitted"]]
    next_step: str | None
    waiting: bool  # Pilao is working on it (DCE read, analysis, drafting)


class ResultsOut(BaseModel):
    deposited: int  # offers submitted, with or without their result
    won: int
    lost: int
    submitted: int  # awaiting their result
    success_rate: float | None  # won / (won + lost), None before the first result
    amount_won_cents: int  # sum of the offers' amounts of the bids won (€ HT)


class TimeSavedOut(BaseModel):
    bids: int  # bids where both durations are filled in
    minutes_with_pilao: int
    minutes_usual: int
    minutes_saved: int


class DashboardOut(BaseModel):
    actions: list[ActionOut]  # what to do now, most urgent first
    getting_started: list[StepOut]  # the first steps of a new account; empty once done
    new_tenders: int  # matched these last 7 days, still open
    best_tenders: list[TenderMatchOut]
    tenders_connected: bool  # False while no notice has ever been loaded (BOAMP/TED)
    bids: list[BidProgressOut]  # in progress, then awaiting their result
    results: ResultsOut
    time_saved: TimeSavedOut


@router.get("/dashboard")
def dashboard(ctx: CurrentAuth, db: ScopedDb) -> DashboardOut:
    """US-5.3: what to do now, new notices, bids and their step, results."""
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
    board = svc.build(db, ctx.org)
    count = {s: sum(1 for b in board.all_bids if b.status == s) for s in ("won", "lost")}
    submitted = sum(1 for b in board.all_bids if b.status == "submitted")
    won, lost = count["won"], count["lost"]
    saved = feedback_svc.time_saved(db)
    return DashboardOut(
        actions=[ActionOut(**vars(a)) for a in board.actions],
        getting_started=[StepOut(**vars(s)) for s in board.getting_started],
        new_tenders=len(fresh),
        best_tenders=[match_out(m, t) for m, t in fresh[:3]],
        tenders_connected=db.scalar(select(Tender.id).limit(1)) is not None,
        bids=[
            BidProgressOut(
                id=f.id,
                title=f.title,
                buyer_name=f.buyer_name,
                deadline_at=f.deadline_at,
                status=f.status,
                done=list(p.done),
                next_step=p.next_step,
                waiting=p.waiting,
            )
            for f, p in board.bids
        ],
        results=ResultsOut(
            deposited=won + lost + submitted,
            won=won,
            lost=lost,
            submitted=submitted,
            success_rate=round(won / (won + lost), 2) if won + lost else None,
            amount_won_cents=sum(
                b.submitted_amount_cents or 0 for b in board.all_bids if b.status == "won"
            ),
        ),
        time_saved=TimeSavedOut(
            bids=saved.bids,
            minutes_with_pilao=saved.minutes_with,
            minutes_usual=saved.minutes_usual,
            minutes_saved=saved.minutes_saved,
        ),
    )
