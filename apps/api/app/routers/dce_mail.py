"""The DCE e-mail address (ADR-055): the company's address, « À classer », the notices."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentAuth, ScopedDb, require_module
from app.core.errors import ApiError
from app.db.models import Bid, InboundMail
from app.routers.files import Storage
from app.schemas.dce_mail import (
    DceMailOut,
    DceNoticeOut,
    FiledOut,
    FileMailIn,
    InboundMailOut,
    NewBidOut,
    SkippedOut,
    SuggestedBidOut,
)
from app.services import inbound_mail as svc
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["dce mail"], dependencies=[Depends(require_module("reponse"))])
Queue = Annotated[JobQueue, Depends(get_job_queue)]


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


def _out(db: ScopedDb, mail: InboundMail) -> InboundMailOut:
    suggested = db.get(Bid, mail.suggested_bid_id) if mail.suggested_bid_id else None
    return InboundMailOut(
        id=mail.id,
        received_at=mail.received_at,
        sender=mail.sender,
        subject=mail.subject,
        kind="dce" if mail.kind == "dce" else "notice",
        attachments=list(mail.attachment_names),
        skipped=[SkippedOut(path=s["path"], reason=s["reason"]) for s in mail.skipped],
        links=list(mail.links),
        suggested_bid=(
            SuggestedBidOut(id=suggested.id, title=suggested.title) if suggested else None
        ),
        note=mail.note,
    )


@router.get("/dce-mail")
def dce_mail(ctx: CurrentAuth, db: ScopedDb) -> DceMailOut:
    return DceMailOut(address=svc.address(db, ctx.org), active=svc.active())


@router.get("/dce-mail/inbox")
def inbox(ctx: CurrentAuth, db: ScopedDb) -> list[InboundMailOut]:
    return [_out(db, m) for m in svc.inbox(db)]


@router.post("/dce-mail/inbox/{mail_id}/file", status_code=202)
def file_mail(
    mail_id: uuid.UUID,
    data: FileMailIn,
    ctx: CurrentAuth,
    db: ScopedDb,
    queue: Queue,
) -> FiledOut:
    bid = _bid(db, data.bid_id)
    version = svc.file_mail(db, ctx.org, ctx.user, mail_id, bid, data.mode, queue)
    return FiledOut(bid_id=bid.id, version=version.version if version else None)


@router.post("/dce-mail/inbox/{mail_id}/new-bid", status_code=201)
def new_bid(
    mail_id: uuid.UUID,
    ctx: CurrentAuth,
    db: ScopedDb,
    queue: Queue,
) -> NewBidOut:
    return NewBidOut(bid_id=svc.bid_from_mail(db, ctx.org, ctx.user, mail_id, queue).id)


@router.delete("/dce-mail/inbox/{mail_id}", status_code=204)
def ignore(mail_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, storage: Storage) -> Response:
    svc.ignore(db, ctx.user, mail_id, storage)
    return Response(status_code=204)


@router.get("/bids/{bid_id}/dce-notices")
def notices(bid_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb) -> list[DceNoticeOut]:
    return [
        DceNoticeOut(
            id=m.id,
            received_at=m.received_at,
            sender=m.sender,
            subject=m.subject,
            links=list(m.links),
        )
        for m in svc.notices(db, _bid(db, bid_id))
    ]


@router.delete("/dce-mail/notices/{mail_id}", status_code=204)
def dismiss(mail_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb) -> Response:
    svc.dismiss_notice(db, mail_id)
    return Response(status_code=204)
