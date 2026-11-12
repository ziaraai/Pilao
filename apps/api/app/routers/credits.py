"""A company's plan and credits (lot 4): common to every company, whatever its modules."""

from fastapi import APIRouter

from app.core.deps import CurrentAuth, ScopedDb
from app.modules import PAID_ACTIONS
from app.schemas.credits import CreditsOut, HistoryOut, PlanBriefOut, PriceOut
from app.services import credits as svc

router = APIRouter(prefix="/credits", tags=["credits"])
HISTORY = 100


@router.get("")
def my_credits(ctx: CurrentAuth, db: ScopedDb) -> CreditsOut:
    plan = svc.plan_of(db, ctx.org)
    balance = svc.org_balance(db, ctx.org)
    prices = svc.prices(db)
    return CreditsOut(
        plan=PlanBriefOut(name=plan.name, description=plan.description, modules=plan.modules),
        monthly_allowance=balance.monthly_allowance,
        monthly_left=balance.monthly_left,
        extra=balance.extra,
        total=balance.total,
        renews_on=balance.renews_on,
        prices=[PriceOut(action=a.key, name=a.name, credits=prices[a.key]) for a in PAID_ACTIONS],
        history=[
            # the note a super admin writes with a top-up stays in the administration
            HistoryOut(**{**vars(r), "reason": None if r.kind == "grant" else r.reason})
            for r in svc.history(db, ctx.org, HISTORY)
        ],
    )
