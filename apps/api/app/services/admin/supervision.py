"""Supervision of the platform (US-6.2): what the super admin sees, read-only.

Every function takes an unscoped session opened read-only (``core.admin_deps.read_only``)
and reads across companies with aggregates, never one query per company.

What never leaves: the text of a memoir, a DCE or a document, a file, the title of a bid,
the lines of a profile (staff, equipment, references, revenue). Only identities, counters,
costs, the users' own feedback and the error message a user already sees.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import (
    AiCall,
    AuditLog,
    AuthToken,
    Bid,
    CompanyProfile,
    ComplianceDocument,
    DataRequest,
    GeneratedDocument,
    Job,
    KnowledgeDocument,
    Memoir,
    Organization,
    TenderImport,
    User,
    UserSession,
)
from app.db.models.platform import PlatformAuditLog
from app.domain import admin_watch
from app.domain.admin_watch import ImportState, JobIssue, OrgActivity
from app.schemas.admin import (
    AccountStateOut,
    ActivityRowOut,
    AiCostModelOut,
    AiCostOrgOut,
    AiCostsOut,
    AiCostTaskOut,
    AiMonthOut,
    AiTaskOut,
    AuditPageOut,
    AuditRowOut,
    CountersOut,
    FeedbackItemOut,
    FeedbackOut,
    ImportPassOut,
    ImportRowOut,
    JobIssueOut,
    OrganizationDetailOut,
    OrganizationRowOut,
    OrgCountersOut,
    OrgIdentityOut,
    OrgUserOut,
    OverviewOut,
    SystemOut,
    TimeSavedRowOut,
    WatchItemOut,
)
from app.services.feedback import recent_feedback, time_saved_by_org

PARIS = ZoneInfo("Europe/Paris")
OPEN_BIDS = ("to_review", "in_progress")
DONE_MEMOIRS = ("ready", "exported")
MEMOIR_EXPORTS = ("memoir_docx", "memoir_pdf", "bundle_zip")
SOURCES = ("ted", "boamp")
MAX_ORGANIZATIONS = 200  # no pagination yet (pilot scale)
CENT = Decimal("0.01")


def euros(value: Decimal | None) -> Decimal:
    return (value or Decimal(0)).quantize(CENT)


def current_month(now: datetime) -> date:
    return now.astimezone(PARIS).date().replace(day=1)


def paris_month_bounds(month: date) -> tuple[datetime, datetime]:
    """Start and end (UTC) of a calendar month of Paris; ``month`` is its first day."""
    start = datetime(month.year, month.month, 1, tzinfo=PARIS)
    following = datetime(month.year + month.month // 12, month.month % 12 + 1, 1, tzinfo=PARIS)
    return start.astimezone(UTC), following.astimezone(UTC)


def months_back(month: date, count: int) -> list[date]:
    """``count`` months ending with ``month``, oldest first."""
    index = month.year * 12 + month.month - 1
    return [date((index - i) // 12, (index - i) % 12 + 1, 1) for i in range(count - 1, -1, -1)]


def _per_org(db: Session, value: Any, model: Any, *where: ColumnElement[bool]) -> dict[Any, Any]:
    """``value`` aggregated per company over ``model``'s rows."""
    rows = db.execute(select(model.org_id, value).where(*where).group_by(model.org_id)).all()
    return {org_id: result for org_id, result in rows}


def last_activity(db: Session) -> dict[uuid.UUID, datetime]:
    """Per company: its latest sign-in or audited action, whichever is the most recent."""
    latest: dict[uuid.UUID, datetime] = {}
    for per_org in (
        _per_org(db, func.max(User.last_login_at), User),
        _per_org(db, func.max(AuditLog.at), AuditLog),
    ):
        for org_id, when in per_org.items():
            if when is not None and (org_id not in latest or when > latest[org_id]):
                latest[org_id] = when
    return latest


def _ai_cost_per_org(db: Session, month: date) -> dict[uuid.UUID | None, Decimal]:
    start, end = paris_month_bounds(month)
    return _per_org(
        db, func.sum(AiCall.cost_eur), AiCall, AiCall.created_at >= start, AiCall.created_at < end
    )


def _deletions_requested(db: Session) -> dict[uuid.UUID, DataRequest]:
    """The deletion scheduled for each company, if any (one at a time)."""
    return {
        req.org_id: req
        for req in db.scalars(
            select(DataRequest).where(
                DataRequest.kind == "deletion", DataRequest.status == "pending"
            )
        )
    }


def _with_access(db: Session) -> set[uuid.UUID]:
    """The companies where someone has created their access (a password)."""
    return set(db.scalars(select(User.org_id).where(User.password_hash.is_not(None)).distinct()))


def job_issues(
    db: Session, now: datetime, errors_since: datetime, org_id: uuid.UUID | None = None
) -> list[JobIssue]:
    """Jobs in error since ``errors_since``, and jobs stuck since then; most recent first.

    A worker killed mid-job (a deploy, a crash) leaves its row « running » for good, and a
    retry adds a new row for the same work: a job only counts as stuck if it is the latest
    one of its ``(kind, ref_id)``, and only within the window, so that it eventually leaves.
    """
    ended = func.coalesce(Job.finished_at, Job.updated_at)
    began = func.coalesce(Job.started_at, Job.created_at)
    limit = now - admin_watch.STUCK_AFTER
    newer = aliased(Job)
    superseded = (
        select(newer.id)
        .where(
            newer.kind == Job.kind,
            newer.ref_id == Job.ref_id,
            newer.created_at > Job.created_at,
        )
        .exists()
    )
    query = (
        select(Job, Organization.name, ended, began)
        .outerjoin(Organization, Organization.id == Job.org_id)
        .where(
            or_(
                and_(Job.status == "error", ended >= errors_since),
                and_(
                    or_(
                        and_(Job.status == "running", began < limit),
                        and_(Job.status == "pending", Job.created_at < limit),
                    ),
                    began >= errors_since,
                    ~superseded,
                ),
            )
        )
    )
    if org_id is not None:
        query = query.where(Job.org_id == org_id)
    issues = [
        JobIssue(
            kind=job.kind,
            org_id=job.org_id,
            org_name=name,
            state="error" if job.status == "error" else "stuck",
            at=ended_at if job.status == "error" else began_at,
            message=job.error if job.status == "error" else None,
        )
        for job, name, ended_at, began_at in db.execute(query).all()
    ]
    return sorted(issues, key=lambda issue: issue.at, reverse=True)


def job_issue_out(issue: JobIssue) -> JobIssueOut:
    return JobIssueOut(
        kind=issue.kind,
        label=admin_watch.job_label(issue.kind),
        org_id=issue.org_id,
        org_name=issue.org_name,
        state=issue.state,
        at=issue.at,
        message=issue.message,
    )


def _imports(db: Session) -> list[tuple[ImportState, TenderImport | None]]:
    """Per source: its state for the watch rules, and its latest pass."""
    settings = get_settings()
    states = []
    for source in SOURCES:
        last = db.scalar(
            select(TenderImport)
            .where(TenderImport.source == source)
            .order_by(TenderImport.created_at.desc())
            .limit(1)
        )
        success = db.scalar(
            select(
                func.max(func.coalesce(TenderImport.finished_at, TenderImport.created_at))
            ).where(TenderImport.source == source, TenderImport.status == "done")
        )
        state = ImportState(
            source=source,
            enabled=bool(getattr(settings, f"{source}_import_enabled")),
            last_status=last.status if last else None,
            last_error=last.error if last else None,
            last_started_at=last.created_at if last else None,
            last_success_at=success,
        )
        states.append((state, last))
    return states


def _time_saved(db: Session) -> list[TimeSavedRowOut]:
    return [
        TimeSavedRowOut(
            name=row.org_name,
            bids=row.bids,
            minutes_saved=row.minutes_saved,
            percent=(
                round(100 * row.minutes_saved / row.minutes_usual) if row.minutes_usual else None
            ),
        )
        for row in time_saved_by_org(db)
    ]


def overview(db: Session, now: datetime) -> OverviewOut:
    orgs = db.execute(
        select(Organization.id, Organization.name, Organization.created_at).order_by(
            Organization.name
        )
    ).all()
    active = last_activity(db)
    week, day = now - timedelta(days=7), now - timedelta(days=1)
    issues = job_issues(db, now, errors_since=day)
    calls, failures = db.execute(
        select(func.count(), func.count().filter(AiCall.success.is_(False))).where(
            AiCall.created_at >= day
        )
    ).one()
    imports = _imports(db)
    watch, more = admin_watch.watch(
        now,
        [state for state, _ in imports],
        issues,
        int(calls),
        int(failures),
        [OrgActivity(o.id, o.name, o.created_at, active.get(o.id)) for o in orgs],
    )
    month_cost = sum(_ai_cost_per_org(db, current_month(now)).values(), Decimal(0))

    logins = _per_org(db, func.count(), AuditLog, AuditLog.action == "login", AuditLog.at >= week)
    bids = _per_org(db, func.count(), Bid, Bid.created_at >= week)
    memoirs = _per_org(db, func.count(), Memoir, Memoir.created_at >= week)
    exports = _per_org(
        db,
        func.count(),
        GeneratedDocument,
        GeneratedDocument.kind.in_(MEMOIR_EXPORTS),
        GeneratedDocument.created_at >= week,
    )
    activity = [
        ActivityRowOut(
            org_id=o.id,
            name=o.name,
            logins=logins.get(o.id, 0),
            bids=bids.get(o.id, 0),
            memoirs=memoirs.get(o.id, 0),
            exports=exports.get(o.id, 0),
        )
        for o in orgs
    ]
    activity.sort(key=lambda a: -(a.logins + a.bids + a.memoirs + a.exports))  # stable: by name

    return OverviewOut(
        counters=CountersOut(
            organizations=len(orgs),
            active_7d=sum(1 for o in orgs if o.id in active and active[o.id] >= week),
            bids_open=db.scalar(
                select(func.count()).select_from(Bid).where(Bid.status.in_(OPEN_BIDS))
            )
            or 0,
            memoirs_done=db.scalar(
                select(func.count()).select_from(Memoir).where(Memoir.status.in_(DONE_MEMOIRS))
            )
            or 0,
            ai_cost_month=euros(month_cost),
            job_errors_24h=sum(1 for issue in issues if issue.state == "error"),
        ),
        watch=[WatchItemOut(**vars(item)) for item in watch],
        more_job_issues=more,
        activity=activity,
        imports=[
            ImportRowOut(
                source=state.source,
                enabled=state.enabled,
                status=state.last_status,
                started_at=state.last_started_at,
                fetched=last.fetched if last else None,
                created=last.created if last else None,
                error=state.last_error,
            )
            for state, last in imports
        ],
        time_saved=_time_saved(db),
    )


def organizations(db: Session, now: datetime) -> list[OrganizationRowOut]:
    orgs = db.scalars(select(Organization).order_by(Organization.name)).all()
    active = last_activity(db)
    users = _per_org(db, func.count(), User)
    bids = _per_org(db, func.count(), Bid)
    memoirs = _per_org(db, func.count(), Memoir, Memoir.status.in_(DONE_MEMOIRS))
    completeness = _per_org(db, func.max(CompanyProfile.completeness_pct), CompanyProfile)
    costs = _ai_cost_per_org(db, current_month(now))
    deletions = _deletions_requested(db)
    with_access = _with_access(db)
    rows = [
        OrganizationRowOut(
            id=o.id,
            name=o.name,
            siret=o.siret,
            city=o.city,
            created_at=o.created_at,
            users=users.get(o.id, 0),
            last_activity_at=active.get(o.id),
            bids=bids.get(o.id, 0),
            memoirs=memoirs.get(o.id, 0),
            completeness_pct=completeness.get(o.id) or 0,
            ai_cost_month=euros(costs.get(o.id)),
            deletion_requested=o.id in deletions,
            suspended=o.suspended_at is not None,
            deletion_due_at=deletions[o.id].due_at if o.id in deletions else None,
            invitation_pending=o.id not in with_access,
        )
        for o in orgs
    ]
    # The latest activity first; a company that never did anything last (then by name).
    rows.sort(
        key=lambda r: (
            r.last_activity_at is None,
            -(r.last_activity_at.timestamp() if r.last_activity_at else 0),
        )
    )
    return rows[:MAX_ORGANIZATIONS]


def organization_exists(db: Session, org_id: uuid.UUID) -> bool:
    return db.get(Organization, org_id) is not None


def _count(db: Session, model: Any, *where: ColumnElement[bool]) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def _ai_months(db: Session, org_id: uuid.UUID, months: Sequence[date]) -> list[AiMonthOut]:
    local_month = func.date_trunc("month", func.timezone("Europe/Paris", AiCall.created_at))
    start, _ = paris_month_bounds(months[0])
    costs = {
        month.strftime("%Y-%m"): cost
        for month, cost in db.execute(
            select(local_month, func.sum(AiCall.cost_eur))
            .where(AiCall.org_id == org_id, AiCall.created_at >= start)
            .group_by(local_month)
        ).all()
    }
    return [AiMonthOut(month=f"{m:%Y-%m}", cost=euros(costs.get(f"{m:%Y-%m}"))) for m in months]


def organization_detail(db: Session, org_id: uuid.UUID, now: datetime) -> OrganizationDetailOut:
    org = db.get_one(Organization, org_id)
    profile = db.scalar(select(CompanyProfile).where(CompanyProfile.org_id == org_id))
    month = current_month(now)
    start, end = paris_month_bounds(month)
    statuses = dict(
        db.execute(
            select(Bid.status, func.count()).where(Bid.org_id == org_id).group_by(Bid.status)
        ).all()
    )
    tasks = db.execute(
        select(AiCall.task, func.count(), func.sum(AiCall.cost_eur))
        .where(AiCall.org_id == org_id, AiCall.created_at >= start, AiCall.created_at < end)
        .group_by(AiCall.task)
        .order_by(func.sum(AiCall.cost_eur).desc())
    ).all()
    users = db.scalars(select(User).where(User.org_id == org_id).order_by(User.created_at)).all()
    deletion = _deletions_requested(db).get(org_id)
    invitations = {  # the latest invitation link of each person, oldest first so the last wins
        t.user_id: t
        for t in db.scalars(
            select(AuthToken)
            .where(AuthToken.org_id == org_id, AuthToken.kind == "invitation")
            .order_by(AuthToken.created_at)
        )
    }
    open_sessions = set(
        db.scalars(
            select(UserSession.user_id).where(
                UserSession.org_id == org_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
    )
    return OrganizationDetailOut(
        account=AccountStateOut(
            suspended_at=org.suspended_at,
            suspension_reason=org.suspension_reason,
            deletion_due_at=deletion.due_at if deletion else None,
            deletion_by=(
                None
                if deletion is None
                else "pilao" if deletion.platform_admin_id is not None else "client"
            ),
        ),
        identity=OrgIdentityOut(
            name=org.name,
            siret=org.siret,
            legal_form=org.legal_form,
            naf_code=org.naf_code,
            postal_code=org.postal_code,
            city=org.city,
            created_at=org.created_at,
            trades=list(profile.trades) if profile else [],
            departments=list(profile.departments) if profile else [],
            last_activity_at=last_activity(db).get(org_id),
            deletion_requested=org_id in _deletions_requested(db),
        ),
        counters=OrgCountersOut(
            bids=sum(statuses.values()),
            bids_by_status=statuses,
            memoirs_done=_count(
                db, Memoir, Memoir.org_id == org_id, Memoir.status.in_(DONE_MEMOIRS)
            ),
            knowledge_documents=_count(db, KnowledgeDocument, KnowledgeDocument.org_id == org_id),
            compliance_valid=_count(
                db,
                ComplianceDocument,
                ComplianceDocument.org_id == org_id,
                ComplianceDocument.status.in_(("valid", "expiring")),
            ),
            compliance_expired=_count(
                db,
                ComplianceDocument,
                ComplianceDocument.org_id == org_id,
                ComplianceDocument.status == "expired",
            ),
            completeness_pct=profile.completeness_pct if profile else 0,
            ai_cost_month=euros(sum((cost for _, _, cost in tasks), Decimal(0))),
        ),
        users=[
            OrgUserOut(
                id=u.id,
                full_name=u.full_name,
                email=u.email,
                role=u.role,
                email_verified=u.email_verified_at is not None,
                last_login_at=u.last_login_at,
                terms_version=u.terms_version,
                status=_user_status(u, invitations.get(u.id), now),
                invited_at=u.created_at if u.password_hash is None else None,
                has_sessions=u.id in open_sessions,
            )
            for u in users
        ],
        ai_months=_ai_months(db, org_id, months_back(month, 6)),
        ai_tasks=[
            AiTaskOut(task=task, label=admin_watch.task_label(task), calls=n, cost=euros(cost))
            for task, n, cost in tasks
        ],
        job_errors=[
            job_issue_out(issue) for issue in job_issues(db, now, now - timedelta(days=30), org_id)
        ],
        feedback=[FeedbackItemOut(**vars(row)) for row in recent_feedback(db, org_id=org_id)],
    )


# --- AI costs, system, feedback ---------------------------------------------------------

PLATFORM = "Plateforme"  # calls made for no company in particular (org_id NULL)
MAX_IMPORT_PASSES = 20
MAX_JOB_ISSUES = 50


def ai_costs(db: Session, month: date | None, now: datetime) -> AiCostsOut:
    """What the AI cost over one calendar month of Paris, by company, task and model."""
    months = months_back(current_month(now), 12)
    month = month or months[-1]
    if month not in months:
        raise ApiError(422, "invalid_month", "Choisissez un des douze derniers mois.")
    start, end = paris_month_bounds(month)
    window = (AiCall.created_at >= start, AiCall.created_at < end)
    cost = func.sum(AiCall.cost_eur)
    by_org = db.execute(
        select(
            AiCall.org_id,
            Organization.name,
            func.count(),
            func.sum(AiCall.input_tokens),
            func.sum(AiCall.output_tokens),
            cost,
        )
        .outerjoin(Organization, Organization.id == AiCall.org_id)
        .where(*window)
        .group_by(AiCall.org_id, Organization.name)
        .order_by(cost.desc(), Organization.name)
    ).all()
    by_task = db.execute(
        select(
            AiCall.task,
            func.count(),
            func.count().filter(AiCall.success.is_(False)),
            func.avg(AiCall.latency_ms),
            cost,
        )
        .where(*window)
        .group_by(AiCall.task)
        .order_by(cost.desc(), AiCall.task)
    ).all()
    by_model = db.execute(
        select(AiCall.model, func.count(), cost)
        .where(*window)
        .group_by(AiCall.model)
        .order_by(cost.desc(), AiCall.model)
    ).all()
    return AiCostsOut(
        month=f"{month:%Y-%m}",
        months=[f"{m:%Y-%m}" for m in reversed(months)],
        total=euros(sum((row[2] for row in by_model), Decimal(0))),
        by_org=[
            AiCostOrgOut(
                org_id=org_id,
                name=name or PLATFORM,
                calls=calls,
                input_tokens=int(tokens_in or 0),
                output_tokens=int(tokens_out or 0),
                cost=euros(spent),
            )
            for org_id, name, calls, tokens_in, tokens_out, spent in by_org
        ],
        by_task=[
            AiCostTaskOut(
                task=task,
                label=admin_watch.task_label(task),
                calls=calls,
                failures=failures,
                avg_latency_ms=round(latency or 0),
                cost=euros(spent),
            )
            for task, calls, failures, latency, spent in by_task
        ],
        by_model=[
            AiCostModelOut(model=model, calls=calls, cost=euros(spent))
            for model, calls, spent in by_model
        ],
    )


def system(db: Session, now: datetime) -> SystemOut:
    """The latest passes of the notice readers, and the jobs that need a look."""
    passes = db.scalars(
        select(TenderImport).order_by(TenderImport.created_at.desc()).limit(MAX_IMPORT_PASSES)
    ).all()
    return SystemOut(
        imports=[
            ImportPassOut(
                source=p.source,
                status=p.status,
                started_at=p.created_at,
                duration_seconds=(
                    round((p.finished_at - p.created_at).total_seconds()) if p.finished_at else None
                ),
                fetched=p.fetched,
                created=p.created,
                updated=p.updated,
                corrected=p.corrected,
                skipped=p.skipped,
                matched=p.matched,
                error=p.error,
            )
            for p in passes
        ],
        jobs=[
            job_issue_out(issue)
            for issue in job_issues(db, now, now - timedelta(days=30))[:MAX_JOB_ISSUES]
        ],
    )


def feedback(db: Session, days: int, now: datetime) -> FeedbackOut:
    """What the users wrote over the last ``days`` days, and the time they saved."""
    items = recent_feedback(db, since=now - timedelta(days=days))
    return FeedbackOut(
        days=days,
        items=[FeedbackItemOut(**vars(row)) for row in items],
        time_saved=_time_saved(db),
    )


def _user_status(
    user: User, invitation: AuthToken | None, now: datetime
) -> Literal["active", "unverified", "invited", "invitation_expired"]:
    """Same reading as the company's own list of colleagues (``members.list_members``)."""
    if user.password_hash is not None:
        return "active" if user.email_verified_at is not None else "unverified"
    if invitation is not None and invitation.used_at is None and invitation.expires_at > now:
        return "invited"
    return "invitation_expired"


# --- Journal (lot 2) -------------------------------------------------------------------------

JOURNAL_PAGE = 100
LOGIN_ACTIONS = (
    "login",
    "login_failed",
    "logout",
    "recovery_code_used",
    "setup_completed",
    "access_reset",
    "disabled",
)


def _cursor(at: datetime, line_id: uuid.UUID) -> str:
    return f"{at.isoformat()}|{line_id}"


def _parse_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        at, line_id = cursor.split("|")
        return datetime.fromisoformat(at), uuid.UUID(line_id)
    except ValueError:
        raise ApiError(422, "invalid_cursor", "Page du journal invalide.") from None


def audit_page(
    db: Session, kind: str, org_id: uuid.UUID | None, cursor: str | None
) -> AuditPageOut:
    """The platform journal, latest first, 100 lines a page; ``kind``: all, logins, accounts.

    The cursor is (time, id): lines written at the same instant are never skipped."""
    query = (
        select(PlatformAuditLog, Organization.name)
        .outerjoin(Organization, Organization.id == PlatformAuditLog.org_id)
        .order_by(PlatformAuditLog.at.desc(), PlatformAuditLog.id.desc())
        .limit(JOURNAL_PAGE + 1)
    )
    if kind == "logins":
        query = query.where(PlatformAuditLog.action.in_(LOGIN_ACTIONS))
    elif kind == "accounts":
        query = query.where(PlatformAuditLog.action.not_in(LOGIN_ACTIONS))
    if org_id is not None:
        query = query.where(PlatformAuditLog.org_id == org_id)
    if cursor is not None:
        at, line_id = _parse_cursor(cursor)
        query = query.where(
            or_(
                PlatformAuditLog.at < at,
                and_(PlatformAuditLog.at == at, PlatformAuditLog.id < line_id),
            )
        )
    found = db.execute(query).all()
    rows = [
        AuditRowOut(
            id=entry.id,
            at=entry.at,
            admin_email=entry.admin_email,
            action=entry.action,
            org_id=entry.org_id,
            org_name=name,
            ip=str(entry.ip) if entry.ip is not None else None,
            meta=dict(entry.meta or {}),
        )
        for entry, name in found[:JOURNAL_PAGE]
    ]
    more = len(found) > JOURNAL_PAGE
    last = rows[-1] if more else None
    return AuditPageOut(rows=rows, next_cursor=_cursor(last.at, last.id) if last else None)
