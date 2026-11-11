"""Account management from the administration (lot 2): routes that change something.

Each route that acts on a company takes :data:`AdminOrg`, a session scoped to that company.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.admin_deps import AdminDb, AdminOrg, CurrentAdmin
from app.core.email import Mailer, get_mailer
from app.integrations.recherche_entreprises import CompanyDirectory, get_company_directory
from app.routers import companies
from app.routers.auth import _client_ip
from app.schemas.admin import (
    AdminCreateOrgIn,
    CreatedOut,
    DeletionPreviewOut,
    OrgDeleteIn,
    OrgDeletionOut,
    SuspendIn,
)
from app.services.admin import accounts as svc
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
