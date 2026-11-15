"""« Ce qu'il manque » (ADR-048): the missing items of a dossier and how to fill them."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentAuth, ScopedDb, require_module
from app.core.errors import ApiError
from app.db.models import Bid
from app.schemas.missing import MissingAnswerIn, MissingKeyIn, MissingOut
from app.services import missing as svc
from app.storage.objects import ObjectStorage, get_storage

router = APIRouter(tags=["missing"], dependencies=[Depends(require_module("reponse"))])
Storage = Annotated[ObjectStorage, Depends(get_storage)]


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


@router.get("/bids/{bid_id}/missing")
def list_missing(bid_id: uuid.UUID, db: ScopedDb) -> MissingOut:
    return svc.missing_for_bid(db, _bid(db, bid_id))


@router.post("/bids/{bid_id}/missing/answer")
def answer_missing(
    bid_id: uuid.UUID, data: MissingAnswerIn, ctx: CurrentAuth, db: ScopedDb
) -> MissingOut:
    """A detail of the tender, answered in place: the marker is replaced word for word."""
    return svc.answer_marker(db, ctx.user, _bid(db, bid_id), data.key, data.answer)


@router.post("/bids/{bid_id}/missing/remove")
def remove_missing(
    bid_id: uuid.UUID, data: MissingKeyIn, ctx: CurrentAuth, db: ScopedDb
) -> MissingOut:
    """« Retirer cette phrase »: the company does not have it, the sentence goes."""
    return svc.remove_marker(db, ctx.user, _bid(db, bid_id), data.key)


@router.post("/bids/{bid_id}/missing/regenerate-documents")
def regenerate_missing_documents(
    bid_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage
) -> MissingOut:
    return svc.regenerate_documents(db, ctx.org, ctx.user, _bid(db, bid_id), storage)
