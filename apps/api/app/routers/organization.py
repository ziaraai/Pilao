import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.deps import CurrentAuth, ScopedDb, require_admin
from app.core.email import Mailer, get_mailer
from app.db.models import DataRequest, File, User
from app.services import org_data as svc
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(prefix="/organization", tags=["organization"])
Admin = Annotated[User, Depends(require_admin)]
Queue = Annotated[JobQueue, Depends(get_job_queue)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


class DataRequestOut(BaseModel):
    id: uuid.UUID
    kind: Literal["export", "deletion"]
    status: Literal["pending", "ready", "error", "cancelled"]
    error: str | None
    file_id: uuid.UUID | None
    filename: str | None
    size_bytes: int | None
    due_at: datetime | None
    created_at: datetime


class DeletionIn(BaseModel):
    confirmation: str = Field(min_length=1, max_length=300)  # the company name, typed


class DeletionOut(BaseModel):
    due_at: datetime | None  # None: no deletion scheduled
    requested_at: datetime | None


def _out(db: ScopedDb, req: DataRequest) -> DataRequestOut:
    record = db.get(File, req.file_id) if req.file_id else None
    return DataRequestOut(
        id=req.id,
        kind=req.kind,
        status=req.status,
        error=req.error,
        file_id=record.id if record else None,
        filename=record.filename if record else None,
        size_bytes=record.size_bytes if record else None,
        due_at=req.due_at,
        created_at=req.created_at,
    )


@router.get("/data-requests")
def list_requests(_: Admin, db: ScopedDb) -> list[DataRequestOut]:
    rows = db.scalars(select(DataRequest).order_by(DataRequest.created_at.desc()).limit(20))
    return [_out(db, r) for r in rows]


@router.post("/exports", status_code=202)
def request_export(user: Admin, db: ScopedDb, queue: Queue) -> DataRequestOut:
    """GDPR access and portability: everything the company has in Pilao, as a ZIP."""
    return _out(db, svc.request_export(db, user, queue))


@router.get("/deletion")
def deletion_status(_: CurrentAuth, db: ScopedDb) -> DeletionOut:
    """For every member: shown as a banner while a deletion is scheduled."""
    req = svc.pending_deletion(db)
    return DeletionOut(
        due_at=req.due_at if req else None, requested_at=req.created_at if req else None
    )


@router.post("/deletion", status_code=202)
def request_deletion(
    data: DeletionIn, user: Admin, ctx: CurrentAuth, db: ScopedDb, mailer: MailerDep
) -> DataRequestOut:
    """GDPR erasure: everything is deleted after the grace period, cancellable until then."""
    return _out(db, svc.request_deletion(db, user, ctx.org, data.confirmation, mailer))


@router.delete("/deletion", status_code=204)
def cancel_deletion(user: Admin, ctx: CurrentAuth, db: ScopedDb, mailer: MailerDep) -> Response:
    svc.cancel_deletion(db, user, ctx.org, mailer)
    return Response(status_code=204)
