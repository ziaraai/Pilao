"""The company's quote for a consultation (ADR-052)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentAuth, ScopedDb, require_module
from app.core.errors import ApiError
from app.db.models import Bid
from app.schemas.files import DownloadUrlOut
from app.schemas.quotes import QuoteDownloadIn, QuoteIn, QuoteOut, QuoteSettingsIn, QuoteStateOut
from app.services import quotes as svc
from app.storage.objects import ObjectStorage, get_storage
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["quotes"], dependencies=[Depends(require_module("reponse"))])
Storage = Annotated[ObjectStorage, Depends(get_storage)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


@router.get("/bids/{bid_id}/quote")
def get_quote(bid_id: uuid.UUID, db: ScopedDb) -> QuoteStateOut:
    return svc.quote_state(db, _bid(db, bid_id))


@router.post("/bids/{bid_id}/quote", status_code=202)
def prepare_quote(
    bid_id: uuid.UUID, data: QuoteIn, ctx: CurrentAuth, db: ScopedDb, queue: Queue
) -> QuoteOut:
    """« Préparer le devis »: paid when the CCTP is read, in the background."""
    return svc.start_quote(db, ctx.user, _bid(db, bid_id), data.summarize, queue, data.number)


@router.put("/bids/{bid_id}/quote")
def update_quote(
    bid_id: uuid.UUID, data: QuoteSettingsIn, ctx: CurrentAuth, db: ScopedDb, queue: Queue
) -> QuoteOut:
    return svc.update_quote(db, ctx.user, _bid(db, bid_id), data, queue)


@router.post("/bids/{bid_id}/quote/download")
def download_quote(
    bid_id: uuid.UUID, data: QuoteDownloadIn, db: ScopedDb, storage: Storage
) -> DownloadUrlOut:
    return svc.download(db, _bid(db, bid_id), data.format, storage)
