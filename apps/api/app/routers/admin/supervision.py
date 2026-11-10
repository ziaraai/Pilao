"""Supervision of the platform, read-only (US-6.2).

Every route reads through ``AdminReadDb``: PostgreSQL refuses any write. The only line
written here is the audit entry of a company page being opened, before the reading starts.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.admin_deps import AdminDb, AdminReadDb, CurrentAdmin, read_only
from app.core.errors import ApiError
from app.routers.auth import _client_ip
from app.schemas.admin import OrganizationDetailOut, OrganizationRowOut, OverviewOut
from app.services.admin import audit
from app.services.admin import supervision as svc

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(db: AdminReadDb) -> OverviewOut:
    return svc.overview(db, datetime.now(UTC))


@router.get("/organizations")
def organizations(db: AdminReadDb) -> list[OrganizationRowOut]:
    return svc.organizations(db, datetime.now(UTC))


@router.get("/organizations/{org_id}")
def organization(
    org_id: uuid.UUID, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> OrganizationDetailOut:
    if not svc.organization_exists(db, org_id):
        raise ApiError(404, "not_found", "Entreprise introuvable.")
    audit.record(db, "organization_viewed", admin=ctx.admin, org_id=org_id, ip=_client_ip(request))
    return svc.organization_detail(read_only(db), org_id, datetime.now(UTC))
