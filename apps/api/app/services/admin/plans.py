"""Plans, action prices and a company's credits, from the administration (lot 4, spec §3.1).

Plans and prices are the platform's own: they are changed in the plain administration session.
What touches one company runs in a session scoped to it (``AdminOrgContext``, lot 2).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import ApiError
from app.db.models import AiCall, CreditEntry, CreditPrice, Organization, Plan, PlatformAdmin
from app.modules import ACTION_BY_KEY, BY_KEY, MODULE_OF_ACTION, MODULES, PAID_ACTIONS
from app.schemas.admin import (
    CreditPriceOut,
    OrgCreditsOut,
    PlanIn,
    PlanOut,
    PlanRefOut,
    PlanUpdateOut,
)
from app.schemas.credits import HistoryOut
from app.services import credits
from app.services.admin import audit
from app.services.admin.context import AdminOrgContext

WINDOW = timedelta(days=30)
ADMIN_HISTORY = 50


def _now() -> datetime:
    return datetime.now(UTC)


# ---------- plans ----------------------------------------------------------------------------


def get_plan(db: Session, plan_id: uuid.UUID) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise ApiError(404, "unknown_plan", "Formule inconnue.")
    return plan


def _counts(db: Session) -> dict[uuid.UUID, int]:
    return dict(
        db.execute(select(Organization.plan_id, func.count()).group_by(Organization.plan_id)).all()
    )


def plan_out(plan: Plan, organizations: int) -> PlanOut:
    return PlanOut(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        modules=plan.modules,
        monthly_credits=plan.monthly_credits,
        welcome_credits=plan.welcome_credits,
        price_note=plan.price_note,
        is_default=plan.is_default,
        archived=plan.archived_at is not None,
        organizations=organizations,
    )


def list_plans(db: Session) -> list[PlanOut]:
    counts = _counts(db)
    plans = sorted(db.scalars(select(Plan)), key=lambda p: p.name.casefold())
    return [plan_out(p, counts.get(p.id, 0)) for p in plans]


def _name_taken(db: Session, name: str, but: uuid.UUID | None = None) -> None:
    query = select(Plan.id).where(func.lower(Plan.name) == name.lower())
    if but is not None:
        query = query.where(Plan.id != but)
    if db.scalar(query) is not None:
        raise ApiError(409, "plan_name_taken", "Une formule porte déjà ce nom.")


def create_plan(db: Session, admin: PlatformAdmin, data: PlanIn, ip: str | None) -> PlanOut:
    _name_taken(db, data.name)
    plan = Plan(**data.model_dump())
    db.add(plan)
    db.flush()
    audit.record(db, "plan_created", admin=admin, ip=ip, meta={"name": plan.name})
    db.commit()
    return plan_out(plan, 0)


def _reordered(current: list[str], added: set[str], removed: set[str]) -> list[str]:
    keep = (set(current) | added) - removed
    return [m.key for m in MODULES if m.key in keep] + [k for k in current if k not in BY_KEY]


def update_plan(
    db: Session, admin: PlatformAdmin, plan_id: uuid.UUID, data: PlanIn, ip: str | None
) -> PlanUpdateOut:
    """Change a plan; its modules and monthly credits apply at once to its companies. Only the
    modules that change are added or removed there: the companies' exceptions stay."""
    plan = get_plan(db, plan_id)
    _name_taken(db, data.name, but=plan.id)
    added, removed = set(data.modules) - set(plan.modules), set(plan.modules) - set(data.modules)
    for key, value in data.model_dump().items():
        setattr(plan, key, value)
    orgs = list(db.scalars(select(Organization).where(Organization.plan_id == plan.id)))
    if added or removed:
        for org in orgs:
            org.modules = _reordered(list(org.modules or ()), added, removed)
    audit.record(
        db, "plan_updated", admin=admin, ip=ip, meta={"name": plan.name, "organizations": len(orgs)}
    )
    db.commit()
    return PlanUpdateOut(plan=plan_out(plan, len(orgs)), organizations_affected=len(orgs))


def set_archived(
    db: Session, admin: PlatformAdmin, plan_id: uuid.UUID, archived: bool, ip: str | None
) -> PlanOut:
    plan = get_plan(db, plan_id)
    if archived and plan.is_default:
        raise ApiError(409, "plan_is_default", "Choisissez d'abord une autre formule par défaut.")
    if (plan.archived_at is not None) != archived:
        plan.archived_at = _now() if archived else None
        action = "plan_archived" if archived else "plan_unarchived"
        audit.record(db, action, admin=admin, ip=ip, meta={"name": plan.name})
        db.commit()
    return plan_out(plan, _counts(db).get(plan.id, 0))


def set_default(db: Session, admin: PlatformAdmin, plan_id: uuid.UUID, ip: str | None) -> PlanOut:
    plan = get_plan(db, plan_id)
    if plan.archived_at is not None:
        raise ApiError(409, "plan_archived", "Cette formule est archivée.")
    if not plan.is_default:
        for other in db.scalars(select(Plan).where(Plan.is_default)):
            other.is_default = False
        db.flush()  # one default at a time (unique index)
        plan.is_default = True
        audit.record(db, "plan_default_set", admin=admin, ip=ip, meta={"name": plan.name})
        db.commit()
    return plan_out(plan, _counts(db).get(plan.id, 0))


# ---------- prices ---------------------------------------------------------------------------


def prices(db: Session, now: datetime | None = None) -> list[CreditPriceOut]:
    since = (now or _now()) - WINDOW
    given_back = aliased(CreditEntry)
    uses = dict(
        db.execute(
            select(CreditEntry.action, func.count())
            .where(
                CreditEntry.kind == "charge",
                CreditEntry.at >= since,
                ~exists().where(given_back.refund_of == CreditEntry.id),
            )
            .group_by(CreditEntry.action)
        ).all()
    )
    costs = dict(
        db.execute(
            select(AiCall.task, func.sum(AiCall.cost_eur))
            .where(AiCall.created_at >= since)
            .group_by(AiCall.task)
        ).all()
    )
    set_ = credits.prices(db)
    out = []
    for a in PAID_ACTIONS:
        used = int(uses.get(a.key, 0))
        cost = costs.get(a.ai_task)
        avg = (Decimal(cost) / used).quantize(Decimal("0.0001")) if used and cost else None
        out.append(
            CreditPriceOut(
                action=a.key,
                name=a.name,
                module=MODULE_OF_ACTION[a.key],
                credits=set_[a.key],
                default_credits=a.default_credits,
                uses_30d=used,
                avg_cost_30d=avg,
            )
        )
    return out


def set_price(
    db: Session, admin: PlatformAdmin, action: str, value: int, ip: str | None
) -> CreditPriceOut:
    paid = ACTION_BY_KEY.get(action)
    if paid is None:
        raise ApiError(404, "unknown_action", "Action inconnue.")
    before = credits.price(db, action)
    row = db.get(CreditPrice, action)
    if row is None:
        db.add(CreditPrice(action=action, credits=value))
    else:
        row.credits = value
    if before != value:
        audit.record(
            db,
            "credit_price_changed",
            admin=admin,
            ip=ip,
            meta={"action": action, "name": paid.name, "from": before, "to": value},
        )
    db.commit()
    return next(p for p in prices(db) if p.action == action)


# ---------- one company ----------------------------------------------------------------------


def org_credits(db: Session, org: Organization) -> OrgCreditsOut:
    plan = credits.plan_of(db, org)
    balance = credits.org_balance(db, org)
    return OrgCreditsOut(
        plan=PlanRefOut(id=plan.id, name=plan.name),
        monthly_allowance=balance.monthly_allowance,
        monthly_left=balance.monthly_left,
        extra=balance.extra,
        total=balance.total,
        renews_on=balance.renews_on,
        history=[HistoryOut(**vars(r)) for r in credits.history(db, org, ADMIN_HISTORY)],
    )


def change_plan(ctx: AdminOrgContext, plan_id: uuid.UUID, ip: str | None) -> OrgCreditsOut:
    plan = credits.assignable_plan(ctx.db, plan_id)
    before = credits.plan_of(ctx.db, ctx.org)
    ctx.db.refresh(ctx.org, with_for_update=True)
    credits.assign_plan(ctx.db, ctx.org, plan)
    if before.id != plan.id:
        audit.record(
            ctx.db,
            "plan_changed",
            admin=ctx.admin,
            org_id=ctx.org.id,
            ip=ip,
            meta={"from": before.name, "to": plan.name},
        )
    ctx.db.commit()
    return org_credits(ctx.db, ctx.org)


def add_credits(ctx: AdminOrgContext, amount: int, reason: str, ip: str | None) -> OrgCreditsOut:
    credits.grant(ctx.db, ctx.org, amount, reason, ctx.admin)
    audit.record(
        ctx.db,
        "credits_added",
        admin=ctx.admin,
        org_id=ctx.org.id,
        ip=ip,
        meta={"amount": amount, "reason": reason},
    )
    ctx.db.commit()
    return org_credits(ctx.db, ctx.org)
