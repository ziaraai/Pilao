"""Account management from the administration (lot 2, spec §2.1 to §2.4).

Every action on a company runs in a session scoped to it (``AdminOrgContext``) and goes through
the company rules (``members``, ``org_data``) on behalf of Pilao (ADR-042). Each one is written
to the platform journal, with the company and the person concerned, never with any content.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Mailer
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import AuthToken, DataRequest, Organization, PlatformAdmin, User, UserSession
from app.integrations.recherche_entreprises import CompanyDirectory
from app.schemas.admin import AdminCreateOrgIn, DeletionPreviewOut, OrgDeletionOut
from app.schemas.members import InviteIn
from app.services import auth as company_auth
from app.services import credits, members, org_data, password_reset
from app.services.actors import PlatformActor
from app.services.admin import audit
from app.services.admin import auth as admin_auth
from app.services.admin.context import AdminOrgContext, actor_of
from app.services.suspension import is_suspended
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

DELETION_REASON = "Suppression programmée par Pilao"
CANCELLED_REASON = "Suppression annulée : réactivez l'entreprise pour lui rendre l'accès."
logger = logging.getLogger("pilao.admin.accounts")


def _now() -> datetime:
    return datetime.now(UTC)


# --- Creating ----------------------------------------------------------------------------


def create_organization(
    db: Session,
    admin: PlatformAdmin,
    data: AdminCreateOrgIn,
    directory: CompanyDirectory | None,
    mailer: Mailer,
    ip: str | None,
) -> tuple[uuid.UUID, bool]:
    """Open a company's space and invite its first person, an administrator without password.

    Returns the company and whether the invitation e-mail left."""
    taken = db.scalar(select(Organization.name).where(Organization.siret == data.siret))
    if taken is not None:
        raise ApiError(409, "siret_taken", f"Ce SIRET a déjà un compte : {taken}.")
    plan = credits.assignable_plan(db, data.plan_id) if data.plan_id else credits.default_plan(db)
    org = Organization(siren=data.siret[:9], siret=data.siret, name=data.name.strip())
    if directory is not None:
        db.rollback()  # no transaction held open during the registry's HTTP call
        company_auth.prefill_from_registry(org, directory)
    db.add(org)
    db.flush()
    credits.assign_plan(db, org, plan)
    audit.record(
        db,
        "organization_created",
        admin=admin,
        org_id=org.id,
        ip=ip,
        meta={"name": org.name, "siret": org.siret, "email": str(data.contact_email).lower()},
    )
    scope_session(db, org.id)
    invite = InviteIn(
        email=data.contact_email, full_name=data.contact_name.strip(), role="org_admin"
    )
    actor = PlatformActor(admin_id=admin.id, email=admin.email)
    return org.id, _invite(db, actor, org, invite, mailer, first_access=True)


def _invite(
    db: Session,
    actor: PlatformActor,
    org: Organization,
    data: InviteIn,
    mailer: Mailer,
    first_access: bool = False,
) -> bool:
    """Invite on behalf of Pilao; ``False`` when the e-mail did not leave (the account exists:
    the invitation is resent from the company's page)."""
    try:
        members.invite(db, actor, org, data, mailer, first_access=first_access)  # commits, mails
    except ApiError as exc:
        if exc.code != "email_unavailable":
            raise
        return False
    return True


# --- Suspending ----------------------------------------------------------------------------


def _block(ctx: AdminOrgContext, reason: str) -> None:
    now = _now()
    ctx.org.suspended_at, ctx.org.suspension_reason = now, reason
    for session in ctx.db.scalars(select(UserSession).where(UserSession.revoked_at.is_(None))):
        session.revoked_at = now  # scoped: this company's sessions only


def suspend(ctx: AdminOrgContext, reason: str, ip: str | None) -> None:
    _block(ctx, reason)
    audit.record(
        ctx.db,
        "organization_suspended",
        admin=ctx.admin,
        org_id=ctx.org.id,
        ip=ip,
        meta={"reason": reason},
    )
    ctx.db.commit()


def reactivate(ctx: AdminOrgContext, queue: JobQueue, ip: str | None) -> None:
    pending = org_data.pending_deletion(ctx.db)
    if pending is not None and pending.platform_admin_id is not None:
        raise ApiError(
            409, "deletion_pending", "Une suppression est programmée : annulez-la d'abord."
        )
    ctx.org.suspended_at = ctx.org.suspension_reason = None
    audit.record(ctx.db, "organization_reactivated", admin=ctx.admin, org_id=ctx.org.id, ip=ip)
    ctx.db.commit()
    try:
        queue.enqueue_rematch_org(ctx.org.id)  # the watch catches up with the open notices
    except Exception:  # reactivated all the same; the next notice import matches it again
        logger.exception("reactivation of %s: could not queue the watch", ctx.org.id)


# --- Deleting ------------------------------------------------------------------------------


def never_used(db: Session, org_id: uuid.UUID) -> bool:
    """Nobody of the company ever signed in: its space can go at once."""
    used = db.scalar(select(exists().where(User.org_id == org_id, User.last_login_at.is_not(None))))
    return not used


def _by(req: DataRequest) -> Literal["pilao", "client"]:
    return "pilao" if req.platform_admin_id is not None else "client"


def deletion_preview(ctx: AdminOrgContext) -> DeletionPreviewOut:
    req = org_data.pending_deletion(ctx.db)
    if req is not None:
        return DeletionPreviewOut(mode="scheduled", due_at=req.due_at, pending=True, by=_by(req))
    if never_used(ctx.db, ctx.org.id):
        return DeletionPreviewOut(mode="immediate", due_at=None, pending=False, by=None)
    due = _now() + timedelta(days=get_settings().deletion_grace_days)
    return DeletionPreviewOut(mode="scheduled", due_at=due, pending=False, by=None)


def delete(
    ctx: AdminOrgContext,
    confirmation: str,
    code: str,
    storage: ObjectStorage,
    mailer: Mailer,
    ip: str | None,
) -> OrgDeletionOut:
    db, org = ctx.db, ctx.org
    org_data.check_confirmation(org, confirmation)  # a typo does not spend a code
    if org_data.pending_deletion(db) is not None:
        raise ApiError(409, "deletion_pending", "La suppression est déjà programmée.")
    admin_auth.confirm_code(db, ctx.admin, ctx.session, code, ip)
    # Decided with the company's users locked: a sign-in that already wrote its time is seen
    # (the lock waits for it), a later one waits for the erasure. Decision, journal line and
    # erasure are one transaction.
    db.execute(select(User.id).where(User.org_id == org.id).with_for_update())
    if never_used(db, org.id):
        audit.record(
            db,
            "organization_deleted",
            admin=ctx.admin,
            org_id=org.id,
            ip=ip,
            meta={"mode": "immediate", "name": org.name},
        )
        if not org_data.erase_organization(db, org.id, storage, requested_at=_now()):
            db.rollback()  # nothing claims it is gone; the code is not spent either
            raise ApiError(
                503, "erasure_interrupted", "Suppression des fichiers interrompue : réessayez."
            )
        return OrgDeletionOut(mode="immediate", due_at=None)
    if org.suspended_at is None:
        _block(ctx, DELETION_REASON)
    audit.record(
        db,
        "organization_deleted",
        admin=ctx.admin,
        org_id=org.id,
        ip=ip,
        meta={"mode": "scheduled", "name": org.name},
    )
    req = org_data.request_deletion(db, actor_of(ctx), org, confirmation, mailer)  # commits
    return OrgDeletionOut(mode="scheduled", due_at=req.due_at)


def cancel_deletion(ctx: AdminOrgContext, mailer: Mailer, ip: str | None) -> None:
    req = org_data.pending_deletion(ctx.db)
    by = _by(req) if req is not None else None
    audit.record(
        ctx.db, "deletion_cancelled", admin=ctx.admin, org_id=ctx.org.id, ip=ip, meta={"by": by}
    )
    if ctx.org.suspension_reason == DELETION_REASON:
        ctx.org.suspension_reason = CANCELLED_REASON  # still suspended: « Réactiver » is explicit
    org_data.cancel_deletion(ctx.db, actor_of(ctx), ctx.org, mailer)  # 404 if none; commits


# --- A company's users -----------------------------------------------------------------------


def _journal(ctx: AdminOrgContext, action: str, user: User, ip: str | None, **meta: str) -> None:
    audit.record(
        ctx.db,
        action,
        admin=ctx.admin,
        org_id=ctx.org.id,
        ip=ip,
        meta={"user_id": str(user.id), "email": user.email, **meta},
    )


def _sends(ctx: AdminOrgContext) -> None:
    """Nothing is e-mailed on behalf of a suspended company."""
    if is_suspended(ctx.org):
        raise ApiError(
            409, "organization_suspended", "Entreprise suspendue : réactivez-la d'abord."
        )


def invite_user(
    ctx: AdminOrgContext, data: InviteIn, mailer: Mailer, ip: str | None
) -> tuple[uuid.UUID, bool]:
    """The new user and whether the invitation e-mail left."""
    _sends(ctx)
    sent = _invite(ctx.db, actor_of(ctx), ctx.org, data, mailer)
    user = ctx.db.scalar(select(User).where(User.email == str(data.email).lower()))
    assert user is not None  # just created in this company
    _journal(ctx, "user_invited", user, ip, role=user.role)
    ctx.db.commit()
    return user.id, sent


def resend_invitation(
    ctx: AdminOrgContext, user_id: uuid.UUID, mailer: Mailer, ip: str | None
) -> None:
    _sends(ctx)
    members.resend(ctx.db, actor_of(ctx), ctx.org, user_id, mailer)  # commits, then mails
    _journal(ctx, "invitation_resent", members.colleague(ctx.db, user_id), ip)
    ctx.db.commit()


def resend_verification(
    ctx: AdminOrgContext, user_id: uuid.UUID, mailer: Mailer, ip: str | None
) -> None:
    _sends(ctx)
    user = members.colleague(ctx.db, user_id)
    if user.password_hash is None:
        raise ApiError(409, "no_password", "Pas encore d'accès : renvoyez l'invitation.")
    if user.email_verified_at is not None:
        raise ApiError(409, "already_verified", "Adresse déjà confirmée.")
    recent = ctx.db.scalar(
        select(func.count())
        .select_from(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.kind == company_auth.VERIFY_KIND,
            AuthToken.created_at >= _now() - timedelta(hours=1),
        )
    )
    if (recent or 0) >= get_settings().email_verify_max_per_hour:
        raise ApiError(429, "too_many_emails", "Envoi déjà fait : réessayez plus tard.")
    message = company_auth.verification_email(ctx.db, user)
    _journal(ctx, "verification_resent", user, ip)
    ctx.db.commit()
    mailer.send(message)


def send_password_reset(
    ctx: AdminOrgContext, user_id: uuid.UUID, mailer: Mailer, ip: str | None
) -> None:
    _sends(ctx)
    user = members.colleague(ctx.db, user_id)
    if user.password_hash is None:
        raise ApiError(409, "no_password", "Pas encore d'accès : renvoyez l'invitation.")
    _journal(ctx, "password_reset_sent", user, ip)
    password_reset.send_reset_link(ctx.db, user, ctx.org, mailer)  # 429 past the cap; commits


def change_role(ctx: AdminOrgContext, user_id: uuid.UUID, role: str, ip: str | None) -> None:
    user = members.change_role(ctx.db, actor_of(ctx), user_id, role)  # commits
    _journal(ctx, "role_changed", user, ip, role=role)
    ctx.db.commit()


def logout_user(ctx: AdminOrgContext, user_id: uuid.UUID, ip: str | None) -> int:
    closed = members.logout_everywhere(ctx.db, actor_of(ctx), user_id)  # commits
    _journal(ctx, "user_logged_out", members.colleague(ctx.db, user_id), ip)
    ctx.db.commit()
    return closed


def remove_user(ctx: AdminOrgContext, user_id: uuid.UUID, code: str, ip: str | None) -> None:
    user = members.colleague(ctx.db, user_id)  # 404 before asking for a code
    admin_auth.confirm_code(ctx.db, ctx.admin, ctx.session, code, ip)
    _journal(ctx, "user_removed", user, ip)
    members.remove(ctx.db, actor_of(ctx), user_id)  # last administrator refused; commits
