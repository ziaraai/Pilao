"""Feedback from users (P4-02)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentAuth, ScopedDb
from app.core.email import Mailer, get_mailer
from app.schemas.feedback import FeedbackIn, FeedbackOut
from app.services import feedback as svc

router = APIRouter(tags=["feedback"])


@router.post("/feedback", status_code=201)
def send_feedback(
    data: FeedbackIn, db: ScopedDb, ctx: CurrentAuth, mailer: Annotated[Mailer, Depends(get_mailer)]
) -> FeedbackOut:
    item = svc.submit(db, ctx.user, ctx.org, data, mailer)
    return FeedbackOut(id=item.id, kind=item.kind, created_at=item.created_at)
