"""Plans, action prices and a company's credits (lot 4)."""

import uuid

from fastapi import APIRouter, Request

from app.core.admin_deps import AdminDb, AdminOrg, AdminReadDb, CurrentAdmin
from app.core.net import client_ip
from app.schemas.admin import (
    CreditPriceIn,
    CreditPriceOut,
    CreditsGrantIn,
    OrgCreditsOut,
    OrgPlanIn,
    PlanIn,
    PlanOut,
    PlanUpdateOut,
)
from app.services.admin import plans as svc

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/plans")
def list_plans(db: AdminReadDb) -> list[PlanOut]:
    return svc.list_plans(db)


@router.post("/plans", status_code=201)
def create_plan(data: PlanIn, request: Request, ctx: CurrentAdmin, db: AdminDb) -> PlanOut:
    return svc.create_plan(db, ctx.admin, data, client_ip(request))


@router.put("/plans/{plan_id}")
def update_plan(
    plan_id: uuid.UUID, data: PlanIn, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> PlanUpdateOut:
    return svc.update_plan(db, ctx.admin, plan_id, data, client_ip(request))


@router.post("/plans/{plan_id}/archive")
def archive(plan_id: uuid.UUID, request: Request, ctx: CurrentAdmin, db: AdminDb) -> PlanOut:
    return svc.set_archived(db, ctx.admin, plan_id, True, client_ip(request))


@router.post("/plans/{plan_id}/unarchive")
def unarchive(plan_id: uuid.UUID, request: Request, ctx: CurrentAdmin, db: AdminDb) -> PlanOut:
    return svc.set_archived(db, ctx.admin, plan_id, False, client_ip(request))


@router.put("/plans/{plan_id}/default")
def make_default(plan_id: uuid.UUID, request: Request, ctx: CurrentAdmin, db: AdminDb) -> PlanOut:
    return svc.set_default(db, ctx.admin, plan_id, client_ip(request))


@router.get("/credit-prices")
def credit_prices(db: AdminReadDb) -> list[CreditPriceOut]:
    return svc.prices(db)


@router.put("/credit-prices/{action}")
def set_credit_price(
    action: str, data: CreditPriceIn, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> CreditPriceOut:
    return svc.set_price(db, ctx.admin, action, data.credits, client_ip(request))


ORG = "/organizations/{org_id}"


@router.put(ORG + "/plan")
def change_plan(data: OrgPlanIn, request: Request, ctx: AdminOrg) -> OrgCreditsOut:
    return svc.change_plan(ctx, data.plan_id, client_ip(request))


@router.get(ORG + "/credits")
def org_credits(ctx: AdminOrg) -> OrgCreditsOut:
    return svc.org_credits(ctx.db, ctx.org)


@router.post(ORG + "/credits")
def add_credits(data: CreditsGrantIn, request: Request, ctx: AdminOrg) -> OrgCreditsOut:
    return svc.add_credits(ctx, data.amount, data.reason, client_ip(request))
