"""What an administration action on one company works with (lot 2, ADR-042)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Organization, PlatformAdmin, PlatformAdminSession
from app.services.actors import PlatformActor


@dataclass(frozen=True)
class AdminOrgContext:
    """The super admin, and a session scoped to one company.

    The scope is the barrier of the company space (``core.tenancy``): the session only sees, and
    may only write, this company's rows. The platform's own tables are global and stay usable."""

    admin: PlatformAdmin
    session: PlatformAdminSession
    org: Organization
    db: Session


def actor_of(ctx: AdminOrgContext) -> PlatformActor:
    return PlatformActor(admin_id=ctx.admin.id, email=ctx.admin.email)
