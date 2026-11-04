import uuid
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.base import Base
from app.db.models import Certification, Equipment, HumanResource
from app.domain.trades import TRADES
from app.schemas.profile import (
    CertificationIn,
    CertificationOut,
    CompletenessOut,
    EquipmentIn,
    EquipmentOut,
    HumanResourceIn,
    HumanResourceOut,
    ProfileIn,
    ProfileOut,
    TradeOut,
)
from app.services import profile as svc

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/trades")
def list_trades(_: CurrentAuth) -> list[TradeOut]:
    return [
        TradeOut(code=t.code, label=t.label, cpv_codes=list(t.cpv_codes), keywords=list(t.keywords))
        for t in TRADES.values()
    ]


@router.get("")
def get_profile(ctx: CurrentAuth, db: ScopedDb) -> ProfileOut:
    profile = svc.get_or_create_profile(db, ctx.org)
    result = svc.refresh_completeness(db, ctx.org)
    db.commit()
    return _profile_out(profile, result)


@router.put("")
def put_profile(data: ProfileIn, ctx: CurrentAuth, db: ScopedDb) -> ProfileOut:
    result = svc.update_profile(db, ctx.org, ctx.user.id, data)
    return _profile_out(svc.get_or_create_profile(db, ctx.org), result)


@router.get("/completeness")
def get_completeness(ctx: CurrentAuth, db: ScopedDb) -> CompletenessOut:
    profile = svc.get_or_create_profile(db, ctx.org)
    result = svc.compute_completeness(db, ctx.org, profile)
    return CompletenessOut(pct=result.pct, missing=result.missing)


def _profile_out(profile: Any, result: Any) -> ProfileOut:
    return ProfileOut(
        **{k: getattr(profile, k) for k in ProfileOut.model_fields if k != "completeness"},
        completeness=CompletenessOut(pct=result.pct, missing=result.missing),
    )


def add_crud(
    path: str,
    model: type[Base],
    body_in: type[BaseModel],
    body_out: type[BaseModel],
    file_fields: tuple[str, ...] = (),
) -> None:
    """Register list/create/get/update/delete for an org-owned entity under /profile/{path}.

    Every query goes through ``ScopedDb``: another organization's id simply yields a 404.
    """

    def get_or_404(db: ScopedDb, item_id: uuid.UUID) -> Any:
        item = db.get(model, item_id)
        if item is None:
            raise ApiError(404, "not_found", "Élément introuvable.")
        return item

    def apply(db: ScopedDb, ctx: CurrentAuth, item: Any, data: BaseModel) -> None:
        svc.ensure_files_belong_to_org(db, *(getattr(data, f) for f in file_fields))
        for key, value in data.model_dump().items():
            setattr(item, key, value)
        db.add(item)
        db.flush()
        svc.refresh_completeness(db, ctx.org)
        db.commit()

    @router.get(f"/{path}", response_model=list[body_out], name=f"list_{path}")  # type: ignore[valid-type]
    def list_items(db: ScopedDb) -> Any:
        return db.scalars(select(model).order_by(model.created_at)).all()  # type: ignore[attr-defined]

    @router.post(f"/{path}", status_code=201, response_model=body_out, name=f"create_{path}")
    def create_item(data: body_in, db: ScopedDb, ctx: CurrentAuth) -> Any:  # type: ignore[valid-type]
        item = model()
        apply(db, ctx, item, data)
        return item

    @router.get(f"/{path}/{{item_id}}", response_model=body_out, name=f"get_{path}")
    def read_item(item_id: uuid.UUID, db: ScopedDb) -> Any:
        return get_or_404(db, item_id)

    @router.put(f"/{path}/{{item_id}}", response_model=body_out, name=f"update_{path}")
    def update_item(item_id: uuid.UUID, data: body_in, db: ScopedDb, ctx: CurrentAuth) -> Any:  # type: ignore[valid-type]
        item = get_or_404(db, item_id)
        apply(db, ctx, item, data)
        return item

    @router.delete(f"/{path}/{{item_id}}", status_code=204, name=f"delete_{path}")
    def delete_item(item_id: uuid.UUID, db: ScopedDb, ctx: CurrentAuth) -> Response:
        db.delete(get_or_404(db, item_id))
        db.flush()
        svc.refresh_completeness(db, ctx.org)
        db.commit()
        return Response(status_code=204)


add_crud("human-resources", HumanResource, HumanResourceIn, HumanResourceOut)
add_crud("equipment", Equipment, EquipmentIn, EquipmentOut, file_fields=("spec_file_id",))
add_crud(
    "certifications", Certification, CertificationIn, CertificationOut, file_fields=("file_id",)
)
