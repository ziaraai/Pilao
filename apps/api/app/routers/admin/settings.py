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
    ModelChoiceIn,
    ModelSettingOut,
    SettingsOut,
)
from app.services.admin import settings as svc

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
    return svc.set_api_key(db, ctx.admin, client, data.key, client_ip(request))


@router.delete("/api-key", status_code=204)
def reset_key(request: Request, ctx: CurrentAdmin, db: AdminDb) -> Response:
    svc.reset_api_key(db, ctx.admin, client_ip(request))
    return Response(status_code=204)
