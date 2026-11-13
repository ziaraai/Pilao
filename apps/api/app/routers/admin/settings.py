"""Platform settings (lot 5, ADR-044): AI models, the OpenRouter key, imports, general."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.ai.openrouter import OpenRouter, get_openrouter
from app.core.admin_deps import AdminDb, AdminReadDb, CurrentAdmin
from app.core.net import client_ip
from app.schemas.admin import (
    ApiKeyIn,
    ApiKeyOut,
    CatalogueModelOut,
    DceRobotSettingOut,
    DceRobotSwitchIn,
    GeneralSettingOut,
    GeneralValueIn,
    ImportSettingOut,
    ImportSwitchIn,
    ModelChoiceIn,
    ModelSettingOut,
    SettingsOut,
)
from app.services.admin import settings as svc
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(prefix="/admin/settings", tags=["admin"])
Client = Annotated[OpenRouter, Depends(get_openrouter)]


@router.get("")
def settings_state(db: AdminReadDb, client: Client) -> SettingsOut:
    return svc.state(db, client)


@router.get("/catalogue")
def models_catalogue(task: str, _: CurrentAdmin, client: Client) -> list[CatalogueModelOut]:
    return svc.catalogue(client, task)


@router.put("/models/{task}")
def choose_model(
    task: str, data: ModelChoiceIn, request: Request, ctx: CurrentAdmin, db: AdminDb, client: Client
) -> ModelSettingOut:
    return svc.set_model(db, ctx.admin, client, task, data.model_id, client_ip(request))


@router.delete("/models/{task}", status_code=204)
def reset_model(task: str, request: Request, ctx: CurrentAdmin, db: AdminDb) -> Response:
    svc.reset_model(db, ctx.admin, task, client_ip(request))
    return Response(status_code=204)


@router.put("/api-key")
def replace_key(
    data: ApiKeyIn, request: Request, ctx: CurrentAdmin, db: AdminDb, client: Client
) -> ApiKeyOut:
    return svc.set_api_key(db, ctx, client, data.key, data.code, client_ip(request))


@router.delete("/api-key", status_code=204)
def reset_key(request: Request, ctx: CurrentAdmin, db: AdminDb) -> Response:
    svc.reset_api_key(db, ctx.admin, client_ip(request))
    return Response(status_code=204)


@router.put("/imports/{source}")
def switch_import(
    source: str, data: ImportSwitchIn, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> ImportSettingOut:
    return svc.set_import(db, ctx.admin, source, data.enabled, client_ip(request))


@router.delete("/imports/{source}", status_code=204)
def reset_import(source: str, request: Request, ctx: CurrentAdmin, db: AdminDb) -> Response:
    svc.reset_import(db, ctx.admin, source, client_ip(request))
    return Response(status_code=204)


@router.post("/imports/{source}/run", status_code=202)
def import_now(
    source: str,
    request: Request,
    ctx: CurrentAdmin,
    db: AdminDb,
    queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> Response:
    svc.start_import(db, ctx.admin, queue, source, client_ip(request))
    return Response(status_code=202)


@router.put("/dce-robot")
def switch_dce_robot(
    data: DceRobotSwitchIn, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> DceRobotSettingOut:
    """The DCE robot on or off for every company (spec « Récupération des DCE », § 4.5)."""
    return svc.set_dce_robot(db, ctx.admin, data.enabled, client_ip(request))


@router.delete("/dce-robot", status_code=204)
def reset_dce_robot(request: Request, ctx: CurrentAdmin, db: AdminDb) -> Response:
    svc.reset_dce_robot(db, ctx.admin, client_ip(request))
    return Response(status_code=204)


@router.put("/general/{name}")
def change_general(
    name: str, data: GeneralValueIn, request: Request, ctx: CurrentAdmin, db: AdminDb
) -> GeneralSettingOut:
    return svc.set_general(db, ctx.admin, name, data.value, client_ip(request))


@router.delete("/general/{name}", status_code=204)
def reset_general(name: str, request: Request, ctx: CurrentAdmin, db: AdminDb) -> Response:
    svc.reset_general(db, ctx.admin, name, client_ip(request))
    return Response(status_code=204)
