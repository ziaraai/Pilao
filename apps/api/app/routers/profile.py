import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.base import Base
from app.db.models import Certification, CompanyReference, Equipment, HumanResource
from app.domain.company import vat_number
from app.domain.trades import TRADES
from app.schemas.profile import (
    CertificationIn,
    CertificationOut,
    CompanyIn,
    CompanyOut,
    CompletenessOut,
    EquipmentIn,
    EquipmentOut,
    HumanResourceIn,
    HumanResourceOut,
    ImportErrorOut,
    ImportReportOut,
    ProfileIn,
    ProfileOut,
    ReferenceIn,
    ReferenceOut,
    TradeOut,
)
from app.services import profile as svc
from app.services import reference_import as xl
from app.workers.queue import JobQueue, get_job_queue

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
def put_profile(
    data: ProfileIn,
    ctx: CurrentAuth,
    db: ScopedDb,
    queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> ProfileOut:
    profile, result = svc.update_profile(db, ctx.org, ctx.user.id, data, queue)
    return _profile_out(profile, result)


def _company_out(org: Any) -> CompanyOut:
    return CompanyOut.model_validate(
        {**{k: getattr(org, k) for k in CompanyOut.model_fields if k != "vat_number"}}
        | {"vat_number": vat_number(org.siren)}
    )


@router.get("/company")
def get_company(ctx: CurrentAuth) -> CompanyOut:
    return _company_out(ctx.org)


@router.put("/company")
def put_company(data: CompanyIn, ctx: CurrentAuth, db: ScopedDb) -> CompanyOut:
    """Identity and layout used by DC1/DC2 and the Word export (logo, colour)."""
    svc.update_company(db, ctx.org, ctx.user.id, data)
    return _company_out(ctx.org)


@router.get("/completeness")
def get_completeness(ctx: CurrentAuth, db: ScopedDb) -> CompletenessOut:
    profile = svc.get_or_create_profile(db, ctx.org)
    result = svc.compute_completeness(db, ctx.org, profile)
    return CompletenessOut(pct=result.pct, missing=result.missing, missing_keys=result.missing_keys)


def _profile_out(profile: Any, result: Any) -> ProfileOut:
    return ProfileOut(
        **{k: getattr(profile, k) for k in ProfileOut.model_fields if k != "completeness"},
        completeness=CompletenessOut(
            pct=result.pct, missing=result.missing, missing_keys=result.missing_keys
        ),
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

    entity = model.__tablename__

    def apply(db: ScopedDb, ctx: CurrentAuth, item: Any, data: BaseModel, action: str) -> None:
        ids: list[Any] = []
        for f in file_fields:
            value = getattr(data, f)
            ids.extend(value if isinstance(value, list) else [value])
        svc.ensure_files_belong_to_org(db, *ids)
        for key, value in data.model_dump().items():
            setattr(item, key, value)
        db.add(item)
        db.flush()
        svc.audit(db, ctx.user.id, action, entity, item.id)
        svc.refresh_completeness(db, ctx.org)
        db.commit()

    @router.get(f"/{path}", response_model=list[body_out], name=f"list_{path}")  # type: ignore[valid-type]
    def list_items(db: ScopedDb) -> Any:
        return db.scalars(select(model).order_by(model.created_at)).all()  # type: ignore[attr-defined]

    @router.post(f"/{path}", status_code=201, response_model=body_out, name=f"create_{path}")
    def create_item(data: body_in, db: ScopedDb, ctx: CurrentAuth) -> Any:  # type: ignore[valid-type]
        item = model()
        apply(db, ctx, item, data, "create")
        return item

    @router.get(f"/{path}/{{item_id}}", response_model=body_out, name=f"get_{path}")
    def read_item(item_id: uuid.UUID, db: ScopedDb) -> Any:
        return get_or_404(db, item_id)

    @router.put(f"/{path}/{{item_id}}", response_model=body_out, name=f"update_{path}")
    def update_item(item_id: uuid.UUID, data: body_in, db: ScopedDb, ctx: CurrentAuth) -> Any:  # type: ignore[valid-type]
        item = get_or_404(db, item_id)
        apply(db, ctx, item, data, "update")
        return item

    @router.delete(f"/{path}/{{item_id}}", status_code=204, name=f"delete_{path}")
    def delete_item(item_id: uuid.UUID, db: ScopedDb, ctx: CurrentAuth) -> Response:
        db.delete(get_or_404(db, item_id))
        svc.audit(db, ctx.user.id, "delete", entity, item_id)
        db.flush()
        svc.refresh_completeness(db, ctx.org)
        db.commit()
        return Response(status_code=204)


add_crud("human-resources", HumanResource, HumanResourceIn, HumanResourceOut)
add_crud("equipment", Equipment, EquipmentIn, EquipmentOut, file_fields=("spec_file_id",))
add_crud(
    "certifications", Certification, CertificationIn, CertificationOut, file_fields=("file_id",)
)


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# Declared before the generic CRUD so "/references/template.xlsx" is not read as an item id.
@router.get("/references/template.xlsx")
def references_template(_: CurrentAuth) -> Response:
    return Response(
        xl.build_template(),
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="modele-references-pilao.xlsx"'},
    )


# Plain ``def``: workbook parsing and the DB session are blocking, so FastAPI runs this in
# its thread pool instead of stalling the event loop for every other request.
@router.post("/references/import")
def import_references(
    file: UploadFile,
    ctx: CurrentAuth,
    db: ScopedDb,
    dry_run: Annotated[bool, Query()] = False,
) -> ImportReportOut:
    """Import the valid rows and report the others (``dry_run`` validates without saving)."""
    content = file.file.read(xl.MAX_BYTES + 1)
    results, ignored = xl.parse_workbook(content)
    valid = [r for r in results if r.data is not None]
    if not dry_run and valid:
        for r in valid:
            assert r.data is not None
            db.add(CompanyReference(**r.data.model_dump()))
        svc.audit(db, ctx.user.id, "import", "company_reference", meta={"created": len(valid)})
        db.flush()
        svc.refresh_completeness(db, ctx.org)
        db.commit()
    return ImportReportOut(
        dry_run=dry_run,
        total=len(results),
        created=0 if dry_run else len(valid),
        errors=[ImportErrorOut(row=r.row, message=r.error or "") for r in results if r.error],
        ignored_columns=ignored,
    )


add_crud("references", CompanyReference, ReferenceIn, ReferenceOut, file_fields=("photo_file_ids",))
