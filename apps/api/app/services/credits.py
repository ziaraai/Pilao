"""A company's credits (lot 4, ADR-043): the only place that writes ``credit_entries``.

The balance is computed from the ledger and the company's plan (``app.domain.credits``). A paid
action takes its credits when it starts (``charge``), in the transaction that creates its work;
a work that fails gives them back (``refund``).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session, aliased

from app.core import runtime
from app.core.errors import ApiError
from app.db.models import (
    Bid,
    CreditEntry,
    CreditPrice,
    Job,
    MemoirSection,
    Organization,
    Plan,
    PlatformAdmin,
    User,
)
from app.domain.credits import (
    Balance,
    InsufficientCredits,
    Ledger,
    compute_balance,
    paris_month,
    refund_parts,
    split_charge,
)
from app.modules import ACTION_BY_KEY, BY_KEY, MODULES, PAID_ACTIONS

WELCOME_REASON = "Crédits offerts"


def _now() -> datetime:
    return datetime.now(UTC)


def contact_sentence() -> str:
    support = str(runtime.effective("support_email") or "").strip()
    return f"Contactez Pilao : {support}." if support else "Contactez Pilao."


def credits_exhausted_error(needed: int, left: int) -> ApiError:
    unit = "crédit" if needed == 1 else "crédits"
    return ApiError(
        402,
        "credits_exhausted",
        f"Il faut {needed} {unit}, il vous en reste {left}. {contact_sentence()}",
    )


# ---------- plans ----------------------------------------------------------------------------


def default_plan(db: Session) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.is_default))
    if plan is None:  # the migration creates one and the administration always keeps one
        raise RuntimeError("no default plan")
    return plan


def assignable_plan(db: Session, plan_id: uuid.UUID) -> Plan:
    """A plan that may be given to a company: it exists and is not archived."""
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise ApiError(404, "unknown_plan", "Formule inconnue.")
    if plan.archived_at is not None:
        raise ApiError(409, "plan_archived", "Cette formule est archivée.")
    return plan


def plan_of(db: Session, org: Organization) -> Plan:
    return db.get_one(Plan, org.plan_id)


def plan_modules(plan: Plan, current: list[str]) -> list[str]:
    """The modules of ``plan`` in the registry's order, plus the keys this code does not know
    (ignored, never erased: lot 3)."""
    wanted = set(plan.modules)
    unknown = [k for k in current if k not in BY_KEY]
    return [m.key for m in MODULES if m.key in wanted] + unknown


def assign_plan(db: Session, org: Organization, plan: Plan) -> None:
    """Give ``plan`` to the company: its modules (exceptions dropped) and, the first time ever,
    its welcome credits. Its monthly allowance applies at once (the balance is computed)."""
    org.plan_id = plan.id
    org.modules = plan_modules(plan, list(org.modules or ()))
    db.flush()
    give_welcome(db, org, plan)


def give_welcome(db: Session, org: Organization, plan: Plan | None = None) -> CreditEntry | None:
    plan = plan or plan_of(db, org)
    if org.welcome_credits_at is not None or plan.welcome_credits <= 0:
        return None
    now = _now()
    entry = CreditEntry(
        org_id=org.id, kind="welcome", extra=plan.welcome_credits, reason=WELCOME_REASON, at=now
    )
    org.welcome_credits_at = now
    db.add(entry)
    db.flush()
    return entry


# ---------- balance and prices ---------------------------------------------------------------


def org_balance(db: Session, org: Organization, now: datetime | None = None) -> Balance:
    now = now or _now()
    plan = plan_of(db, org)
    month = paris_month(now)
    used, extra = db.execute(
        select(
            func.coalesce(
                func.sum(case((CreditEntry.month == month, CreditEntry.monthly), else_=0)), 0
            ),
            func.coalesce(func.sum(CreditEntry.extra), 0),
        ).where(CreditEntry.org_id == org.id)
    ).one()
    return compute_balance(
        plan.monthly_credits, plan.welcome_credits, [Ledger(int(used), int(extra), month)], now
    )


def totals(db: Session, now: datetime | None = None) -> dict[uuid.UUID, int]:
    """Every company's balance, in two queries (the administration's list)."""
    month = paris_month(now or _now())
    sums = {
        org_id: (int(used), int(extra))
        for org_id, used, extra in db.execute(
            select(
                CreditEntry.org_id,
                func.coalesce(
                    func.sum(case((CreditEntry.month == month, CreditEntry.monthly), else_=0)), 0
                ),
                func.coalesce(func.sum(CreditEntry.extra), 0),
            ).group_by(CreditEntry.org_id)
        )
    }
    out = {}
    for org_id, allowance in db.execute(
        select(Organization.id, Plan.monthly_credits).join(Plan, Plan.id == Organization.plan_id)
    ):
        used, extra = sums.get(org_id, (0, 0))
        out[org_id] = max(0, allowance + used) + max(0, extra)
    return out


def price(db: Session, action: str) -> int:
    row = db.get(CreditPrice, action)
    return row.credits if row is not None else ACTION_BY_KEY[action].default_credits


def prices(db: Session) -> dict[str, int]:
    set_ = {p.action: p.credits for p in db.scalars(select(CreditPrice))}
    return {a.key: set_.get(a.key, a.default_credits) for a in PAID_ACTIONS}


# ---------- movements ------------------------------------------------------------------------


def lock_org(db: Session, org_id: uuid.UUID) -> None:
    """One paid action at a time per company, until the caller commits. Taken first, before
    the « one at a time » check of the action, so the second click waits and then sees the
    first one's work. FOR NO KEY UPDATE: the rows a paid action inserts (works, jobs, credit
    lines) lock the company in key-share mode through their foreign key, which never
    conflicts with this lock: two requests cannot deadlock on it."""
    db.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update(key_share=True)
    )


def charge(
    db: Session,
    org: Organization,
    action: str,
    *,
    user_id: uuid.UUID | None,
    bid_id: uuid.UUID | None = None,
    ref_id: uuid.UUID | None = None,
) -> CreditEntry | None:
    """Take the price of ``action``; nothing when it is free. The caller commits with the work
    it creates. Raises 402 ``credits_exhausted`` when the balance is too low."""
    cost = price(db, action)
    if cost <= 0:
        return None
    lock_org(db, org.id)  # one charge at a time per company: no two spend the same credits
    now = _now()
    try:
        monthly, extra = split_charge(org_balance(db, org, now), cost)
    except InsufficientCredits as exc:
        raise credits_exhausted_error(exc.needed, exc.left) from None
    entry = CreditEntry(
        org_id=org.id,
        kind="charge",
        action=action,
        monthly=-monthly,
        extra=-extra,
        month=paris_month(now),
        bid_id=bid_id,
        user_id=user_id,
        ref_id=ref_id,
        at=now,
    )
    db.add(entry)
    db.flush()
    return entry


def refund(db: Session, entry: CreditEntry, reason: str) -> CreditEntry | None:
    """Give back what ``entry`` took, where it took it; once only."""
    if entry.kind != "charge" or entry.month is None:
        return None
    if db.scalar(select(CreditEntry.id).where(CreditEntry.refund_of == entry.id)):
        return None
    monthly, extra, month = refund_parts(entry.monthly, entry.extra, entry.month, _now())
    back = CreditEntry(
        org_id=entry.org_id,
        kind="refund",
        action=entry.action,
        monthly=monthly,
        extra=extra,
        month=month,
        bid_id=entry.bid_id,
        user_id=entry.user_id,
        ref_id=entry.ref_id,
        refund_of=entry.id,
        reason=reason,
    )
    db.add(back)
    db.flush()
    return back


def grant(
    db: Session, org: Organization, amount: int, reason: str, admin: PlatformAdmin | None
) -> CreditEntry:
    """Extra credits added by Pilao: they never expire. ``admin`` is None for a grant made by
    the platform itself (the phase 0 evaluation)."""
    entry = CreditEntry(
        org_id=org.id,
        kind="grant",
        extra=amount,
        reason=reason,
        platform_admin_id=admin.id if admin else None,
    )
    db.add(entry)
    db.flush()
    return entry


def free_relaunches(
    db: Session, memoir_id: uuid.UUID, sections: Sequence[MemoirSection]
) -> set[uuid.UUID]:
    """The failed chapters whose relaunch costs nothing: their failure kept its credits. A
    failure that gave them back makes the relaunch paid again — the chapter's last paid
    regeneration refunded, or, for a chapter never regenerated, the whole drafting refunded
    (every chapter failed). Otherwise a memoir could be written chapter by chapter for free."""
    failed = [s.id for s in sections if s.status == "error"]
    if not failed:
        return set()
    last_regeneration: dict[uuid.UUID, uuid.UUID] = {}
    for ref_id, entry_id in db.execute(
        select(CreditEntry.ref_id, CreditEntry.id)
        .where(
            CreditEntry.kind == "charge",
            CreditEntry.action == "chapter_regeneration",
            CreditEntry.ref_id.in_(failed),
        )
        .order_by(CreditEntry.at)
    ):
        if ref_id is not None:  # always set here: the query filters on it
            last_regeneration[ref_id] = entry_id  # the latest wins
    drafting = db.scalars(
        select(CreditEntry.id)
        .where(
            CreditEntry.kind == "charge",
            CreditEntry.action == "memoir_generation",
            CreditEntry.ref_id == memoir_id,
        )
        .order_by(CreditEntry.at.desc())
    ).first()
    charges = [*last_regeneration.values(), *([drafting] if drafting else [])]
    refunded = set(
        db.scalars(select(CreditEntry.refund_of).where(CreditEntry.refund_of.in_(charges)))
    )
    drafting_kept = drafting is None or drafting not in refunded
    return {
        sid
        for sid in failed
        if (last_regeneration[sid] not in refunded if sid in last_regeneration else drafting_kept)
    }


# The works whose failure gives back their charge: job kind -> (paid action, history line).
REFUNDED_JOBS = {
    "analyze_dce": ("dce_analysis", "Remboursé : l'analyse n'a pas abouti."),
    "draft_memoir_section": ("chapter_regeneration", "Remboursé : la régénération n'a pas abouti."),
    "profile_prefill": ("profile_prefill", "Remboursé : la lecture n'a pas abouti."),
}
DRAFTING_REFUND = "Remboursé : la rédaction n'a pas abouti."


def refund_latest(
    db: Session, action: str, ref_id: uuid.UUID, since: datetime | None, reason: str
) -> CreditEntry | None:
    """Give back the latest charge of ``action`` for ``ref_id`` (made since ``since``) that was
    not given back yet."""
    given_back = aliased(CreditEntry)
    query = (
        select(CreditEntry)
        .where(
            CreditEntry.kind == "charge",
            CreditEntry.action == action,
            CreditEntry.ref_id == ref_id,
            ~exists().where(given_back.refund_of == CreditEntry.id),
        )
        .order_by(CreditEntry.at.desc())
    )
    if since is not None:
        query = query.where(CreditEntry.at >= since)
    for entry in db.scalars(query):
        back = refund(db, entry, reason)
        if back is not None:
            return back
    return None


def refund_failed(db: Session, job: Job) -> None:
    """A work that ends in error gives back what its launch took (called by ``set_job_status``).
    Only a charge made for this very work counts: one made before it started is not touched."""
    found = REFUNDED_JOBS.get(job.kind)
    if found is None or job.ref_id is None:
        return
    action, reason = found
    refund_latest(db, action, job.ref_id, job.created_at, reason)


# ---------- history --------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryRow:
    at: datetime
    kind: str
    action_name: str | None
    bid_title: str | None
    user_name: str | None
    credits: int
    reason: str | None


def history(db: Session, org: Organization, limit: int) -> list[HistoryRow]:
    rows = db.execute(
        select(CreditEntry, Bid.title, User.full_name, User.email)
        .outerjoin(Bid, Bid.id == CreditEntry.bid_id)
        .outerjoin(User, User.id == CreditEntry.user_id)
        .where(CreditEntry.org_id == org.id)
        .order_by(CreditEntry.at.desc(), CreditEntry.id.desc())
        .limit(limit)
    ).all()
    out = []
    for entry, title, full_name, email in rows:
        action = ACTION_BY_KEY.get(entry.action or "")
        who = full_name or email or ("Pilao" if entry.platform_admin_id else None)
        out.append(
            HistoryRow(
                at=entry.at,
                kind=entry.kind,
                action_name=action.name if action else None,
                bid_title=title,
                user_name=who,
                credits=entry.monthly + entry.extra,
                reason=entry.reason,
            )
        )
    return out
