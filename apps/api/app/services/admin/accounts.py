"""Account management from the administration (lot 2, spec §2.1 to §2.4).

Every action on a company runs in a session scoped to it (``AdminOrgContext``) and goes through
the company rules (``members``, ``org_data``) on behalf of Pilao (ADR-042). Each one is written
to the platform journal, with the company and the person concerned, never with any content.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.admin_deps import AdminOrgContext, actor_of
from app.core.config import get_settings
from app.core.email import Mailer
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import DataRequest, Organization, PlatformAdmin, User, UserSession
from app.integrations.recherche_entreprises import CompanyDirectory
from app.schemas.admin import AdminCreateOrgIn, DeletionPreviewOut, OrgDeletionOut
from app.schemas.members import InviteIn
from app.services import members, org_data
from app.services.actors import PlatformActor
from app.services.admin import audit
from app.services.admin import auth as admin_auth
from app.services.auth import _prefill_from_registry
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

DELETION_REASON = "Suppression programmée par Pilao"


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
) -> uuid.UUID:
    """Open a company's space and invite its first person, an administrator without password."""
    taken = db.scalar(select(Organization.name).where(Organization.siret == data.siret))
    if taken is not None:
        raise ApiError(409, "siret_taken", f"Ce SIRET a déjà un compte : {taken}.")
    org = Organization(siren=data.siret[:9], siret=data.siret, name=data.name.strip())
    if directory is not None:
        db.rollback()  # no transaction held open during the registry's HTTP call
        _prefill_from_registry(org, directory)
    db.add(org)
    db.flush()
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
    members.invite(db, actor, org, invite, mailer, first_access=True)  # commits, then mails
    return org.id


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
    queue.enqueue_rematch_org(ctx.org.id)  # the watch catches up with the open notices


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
    # Decided under the company's row lock: a first sign-in cannot slip in between.
    db.execute(select(Organization.id).where(Organization.id == org.id).with_for_update())
    if never_used(db, org.id):
        audit.record(
            db,
            "organization_deleted",
            admin=ctx.admin,
            org_id=org.id,
            ip=ip,
            meta={"mode": "immediate", "name": org.name},
        )
        db.commit()
        if not org_data.erase_organization(db, org.id, storage, requested_at=_now()):
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
    org_data.cancel_deletion(ctx.db, actor_of(ctx), ctx.org, mailer)  # 404 if none; commits
