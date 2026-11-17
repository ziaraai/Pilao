"""Chiffrage (ADR-049): the company's rates and the price files of a dossier."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentAuth, ScopedDb, require_module
from app.core.errors import ApiError
from app.db.models import Bid
from app.schemas.files import DownloadUrlOut
from app.schemas.pricing import (
    PriceSheetOut,
    PricesOut,
    RatesIn,
    RatesOut,
    ServiceOut,
    ServicesIn,
    SheetUpdateIn,
)
from app.services import pricing as svc
from app.storage.objects import ObjectStorage, get_storage
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["pricing"], dependencies=[Depends(require_module("reponse"))])
Storage = Annotated[ObjectStorage, Depends(get_storage)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


@router.get("/profile/rates")
def get_rates(ctx: CurrentAuth, db: ScopedDb) -> RatesOut:
    return svc.rates_out(db, ctx.org.id)


@router.put("/profile/rates")
def put_rates(data: RatesIn, ctx: CurrentAuth, db: ScopedDb) -> RatesOut:
    return svc.save_rates(db, ctx.user, ctx.org.id, data)


@router.get("/profile/services")
def get_services(ctx: CurrentAuth, db: ScopedDb) -> list[ServiceOut]:
    return svc.services_out(db, ctx.org.id)


@router.put("/profile/services")
def put_services(data: ServicesIn, ctx: CurrentAuth, db: ScopedDb) -> list[ServiceOut]:
    return svc.save_services(db, ctx.user, ctx.org.id, data)


@router.get("/bids/{bid_id}/prices")
def list_prices(bid_id: uuid.UUID, db: ScopedDb) -> PricesOut:
    return svc.prices_for_bid(db, _bid(db, bid_id))


@router.post("/bids/{bid_id}/prices/{dce_file_id}/read", status_code=202)
def read_prices(
    bid_id: uuid.UUID, dce_file_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, queue: Queue
) -> PricesOut:
    """« Lire le fichier » (paid): the AI lists the lines to price, in the background."""
    bid = _bid(db, bid_id)
    svc.start_read(db, ctx.user, bid, dce_file_id, queue)
    return svc.prices_for_bid(db, bid)


@router.put("/price-sheets/{sheet_id}")
def update_prices(
    sheet_id: uuid.UUID, data: SheetUpdateIn, ctx: CurrentAuth, db: ScopedDb
) -> PriceSheetOut:
    return svc.update_sheet(db, ctx.user, svc.get_sheet(db, sheet_id), data)


@router.post("/price-sheets/{sheet_id}/export")
def export_prices(
    sheet_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage
) -> DownloadUrlOut:
    """The buyer's file filled with the company's prices (a short-lived link)."""
    return svc.export_filled(db, ctx.org, ctx.user, svc.get_sheet(db, sheet_id), storage)
