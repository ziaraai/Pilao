"""Supervision of the platform, read-only (US-6.2).

Every route reads through ``AdminReadDb``: PostgreSQL refuses any write. The only line
written here is the audit entry of a company page being opened, before the reading starts.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.ai.openrouter import OpenRouter, get_openrouter
from app.core.admin_deps import AdminDb, AdminReadDb, CurrentAdmin, read_only
from app.core.errors import ApiError
from app.core.net import client_ip
from app.schemas.admin import (
    AiCostsOut,
    FeedbackOut,
    OrganizationDetailOut,
    OrganizationRowOut,
    OverviewOut,
    SystemOut,
)
from app.services.admin import audit
from app.services.admin import settings as settings_svc
from app.services.admin import supervision as svc

router = APIRouter(prefix="/admin", tags=["admin"])
FEEDBACK_WINDOWS = (7, 30, 90)  # days


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("/overview")
def overview(
    db: AdminReadDb, client: Annotated[OpenRouter, Depends(get_openrouter)]
) -> OverviewOut:
    alerts = settings_svc.watch_alerts(settings_svc.known_catalogue_ids(client))  # lot 5
    return svc.overview(db, _now(), settings_alerts=alerts)


@router.get("/organizations")
def organizations(db: AdminReadDb) -> list[OrganizationRowOut]:
    return svc.organizations(db, _now())


@router.get("/organizations/{org_id}")
def organization(
    org_id: uuid.UUID, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> OrganizationDetailOut:
    if not svc.organization_exists(db, org_id):
        raise ApiError(404, "not_found", "Entreprise introuvable.")
    audit.record(db, "organization_viewed", admin=ctx.admin, org_id=org_id, ip=client_ip(request))
    return svc.organization_detail(read_only(db), org_id, _now())


@router.get("/ai-costs")
def ai_costs(
    db: AdminReadDb,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
) -> AiCostsOut:
    try:
        wanted = date(int(month[:4]), int(month[5:]), 1) if month else None
    except ValueError as exc:  # "2026-13"
        raise ApiError(422, "invalid_month", "Choisissez un des douze derniers mois.") from exc
    return svc.ai_costs(db, wanted, _now())


@router.get("/system")
def system(db: AdminReadDb) -> SystemOut:
    return svc.system(db, _now())


@router.get("/feedback")
def feedback(db: AdminReadDb, days: int = 30) -> FeedbackOut:
    if days not in FEEDBACK_WINDOWS:
        raise ApiError(422, "invalid_days", "Choisissez 7, 30 ou 90 jours.")
    return svc.feedback(db, days, _now())
