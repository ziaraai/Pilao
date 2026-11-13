"""DCE retrieval from a dossier and the company's choices (spec « Récupération des DCE », § 7.5)."""

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends

from app.core.deps import CurrentAuth, ScopedDb, require_module
from app.core.errors import ApiError
from app.db.models import Bid, Organization
from app.domain.dce_sources import guide, terms_url
from app.schemas.dce_retrieval import (
    ContactIO,
    DceFetchOut,
    DceSourceOut,
    DceWatchOut,
    Mode,
    RetrievalSettingsIO,
    RetrieveIn,
    SourceIn,
)
from app.services import dce_retrieval as svc
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["dce retrieval"], dependencies=[Depends(require_module("reponse"))])
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


def _contact(contact: svc.Contact) -> ContactIO:
    return ContactIO.model_validate(
        {"first_name": contact.first_name, "last_name": contact.last_name, "email": contact.email}
    )


def _settings(org: Organization) -> RetrievalSettingsIO:
    mode, contact = svc.settings_for(org)
    return RetrievalSettingsIO(mode=cast(Mode | None, mode), contact=_contact(contact))


def _source_out(db: ScopedDb, org: Organization, bid: Bid) -> DceSourceOut:
    src = svc.source_for(db, bid)
    fetch = svc.latest_fetch(db, bid.id, src.url) if src else None
    settings = _settings(org)
    return DceSourceOut(
        url=src.url if src else None,
        platform=src.platform if src else None,
        site=src.site if src else None,
        automatic=svc.robot_ready(src),
        home_only=bool(src and src.home_only),
        guide=list(guide(src.platform, bid.reference)) if src else [],
        terms_url=terms_url(src) if src else None,
        robot_enabled=svc.robot_enabled(),
        mode=settings.mode,
        contact=settings.contact,
        last_fetch=DceFetchOut.model_validate(fetch) if fetch else None,
        watch=DceWatchOut.model_validate(bid.dce_watch) if bid.dce_watch else None,
    )


@router.get("/bids/{bid_id}/dce/source")
def get_source(bid_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb) -> DceSourceOut:
    return _source_out(db, ctx.org, _bid(db, bid_id))


@router.put("/bids/{bid_id}/dce/source")
def put_source(bid_id: uuid.UUID, data: SourceIn, ctx: CurrentAuth, db: ScopedDb) -> DceSourceOut:
    """The consultation's link pasted in the dossier (empty: the notice's link again)."""
    bid = svc.set_link(db, ctx.user, _bid(db, bid_id), data.url)
    return _source_out(db, ctx.org, bid)


@router.post("/bids/{bid_id}/dce/retrieve", status_code=202)
def retrieve(
    bid_id: uuid.UUID, data: RetrieveIn, ctx: CurrentAuth, db: ScopedDb, queue: Queue
) -> DceFetchOut:
    """Pilao retrieves the DCE on PLACE or an Atexo platform; poll ``…/dce/source``."""
    contact = (
        svc.Contact(data.contact.first_name, data.contact.last_name, data.contact.email)
        if data.contact is not None
        else None
    )
    fetch = svc.request_retrieval(
        db,
        ctx.org,
        ctx.user,
        _bid(db, bid_id),
        mode=data.mode,
        remember=data.remember,
        contact=contact,
        queue=queue,
    )
    return DceFetchOut.model_validate(fetch)


@router.get("/profile/dce-retrieval")
def get_settings_route(ctx: CurrentAuth) -> RetrievalSettingsIO:
    return _settings(ctx.org)


@router.put("/profile/dce-retrieval")
def put_settings(data: RetrievalSettingsIO, ctx: CurrentAuth, db: ScopedDb) -> RetrievalSettingsIO:
    c = data.contact
    svc.save_settings(
        db, ctx.user, ctx.org, data.mode, svc.Contact(c.first_name, c.last_name, c.email)
    )
    return _settings(ctx.org)
