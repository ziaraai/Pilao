"""Account management from the administration (lot 2): routes that change something.

Each route that acts on a company takes :data:`AdminOrg`, a session scoped to that company.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.admin_deps import AdminDb, AdminOrg, AdminReadDb, CurrentAdmin
from app.core.email import Mailer, get_mailer
from app.integrations.recherche_entreprises import CompanyDirectory, get_company_directory
from app.routers import companies
from app.routers.auth import _client_ip
from app.schemas.admin import (
    AdminCreateOrgIn,
    AuditPageOut,
    CreatedOut,
    DeletionPreviewOut,
    OrgDeleteIn,
    OrgDeletionOut,
    StepUpIn,
    SuspendIn,
)
from app.schemas.members import InviteIn, RoleIn
from app.services.admin import accounts as svc
from app.services.admin import supervision
from app.storage.objects import ObjectStorage, get_storage
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(prefix="/admin", tags=["admin"])
MailerDep = Annotated[Mailer, Depends(get_mailer)]
Directory = Annotated[CompanyDirectory, Depends(get_company_directory)]


@router.get("/companies/lookup")
def company_lookup(
    siret: Annotated[str, Query(pattern=r"^[\d\s]{14,40}$")],
    request: Request,
    directory: Directory,
    _: CurrentAdmin,
) -> companies.LookupOut:
    """The registry, as on the sign-up page: pre-fills the company created by Pilao."""
    return companies.lookup(siret, request, directory)


@router.post("/organizations", status_code=201)
def create_organization(
    data: AdminCreateOrgIn,
    request: Request,
    ctx: CurrentAdmin,
    db: AdminDb,
    directory: Directory,
    mailer: MailerDep,
) -> CreatedOut:
    org_id = svc.create_organization(db, ctx.admin, data, directory, mailer, _client_ip(request))
    return CreatedOut(id=org_id)


@router.post("/organizations/{org_id}/suspend", status_code=204)
def suspend(data: SuspendIn, request: Request, ctx: AdminOrg) -> Response:
    svc.suspend(ctx, data.reason, _client_ip(request))
    return Response(status_code=204)


@router.post("/organizations/{org_id}/reactivate", status_code=204)
def reactivate(
    request: Request, ctx: AdminOrg, queue: Annotated[JobQueue, Depends(get_job_queue)]
) -> Response:
    svc.reactivate(ctx, queue, _client_ip(request))
    return Response(status_code=204)


@router.get("/organizations/{org_id}/deletion")
def deletion_preview(ctx: AdminOrg) -> DeletionPreviewOut:
    return svc.deletion_preview(ctx)


@router.post("/organizations/{org_id}/deletion")
def delete(
    data: OrgDeleteIn,
    request: Request,
    ctx: AdminOrg,
    storage: Annotated[ObjectStorage, Depends(get_storage)],
    mailer: MailerDep,
) -> OrgDeletionOut:
    return svc.delete(ctx, data.confirmation, data.code, storage, mailer, _client_ip(request))


@router.delete("/organizations/{org_id}/deletion", status_code=204)
def cancel_deletion(request: Request, ctx: AdminOrg, mailer: MailerDep) -> Response:
    svc.cancel_deletion(ctx, mailer, _client_ip(request))
    return Response(status_code=204)


# --- A company's users -----------------------------------------------------------------------

USERS = "/organizations/{org_id}/users"


@router.post(USERS, status_code=201)
def invite_user(data: InviteIn, request: Request, ctx: AdminOrg, mailer: MailerDep) -> CreatedOut:
    return CreatedOut(id=svc.invite_user(ctx, data, mailer, _client_ip(request)))


@router.post(USERS + "/{user_id}/invitation", status_code=204)
def resend_invitation(
    user_id: uuid.UUID, request: Request, ctx: AdminOrg, mailer: MailerDep
) -> Response:
    svc.resend_invitation(ctx, user_id, mailer, _client_ip(request))
    return Response(status_code=204)


@router.post(USERS + "/{user_id}/verification", status_code=204)
def resend_verification(
    user_id: uuid.UUID, request: Request, ctx: AdminOrg, mailer: MailerDep
) -> Response:
    svc.resend_verification(ctx, user_id, mailer, _client_ip(request))
    return Response(status_code=204)


@router.post(USERS + "/{user_id}/password-reset", status_code=204)
def send_password_reset(
    user_id: uuid.UUID, request: Request, ctx: AdminOrg, mailer: MailerDep
) -> Response:
    svc.send_password_reset(ctx, user_id, mailer, _client_ip(request))
    return Response(status_code=204)


@router.patch(USERS + "/{user_id}", status_code=204)
def change_role(user_id: uuid.UUID, data: RoleIn, request: Request, ctx: AdminOrg) -> Response:
    svc.change_role(ctx, user_id, data.role, _client_ip(request))
    return Response(status_code=204)


@router.post(USERS + "/{user_id}/logout", status_code=204)
def logout_user(user_id: uuid.UUID, request: Request, ctx: AdminOrg) -> Response:
    svc.logout_user(ctx, user_id, _client_ip(request))
    return Response(status_code=204)


@router.post(USERS + "/{user_id}/remove", status_code=204)
def remove_user(user_id: uuid.UUID, data: StepUpIn, request: Request, ctx: AdminOrg) -> Response:
    """POST, not DELETE: the code travels in the body."""
    svc.remove_user(ctx, user_id, data.code, _client_ip(request))
    return Response(status_code=204)


# --- Journal ---------------------------------------------------------------------------------


@router.get("/audit")
def journal(
    db: AdminReadDb,
    kind: Literal["all", "logins", "accounts"] = "all",
    org_id: uuid.UUID | None = None,
    cursor: str | None = None,
) -> AuditPageOut:
    return supervision.audit_page(db, kind, org_id, cursor)
