"""Colleagues of the organization (US-1.5): every member sees them, administrators manage."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentAuth, ScopedDb, require_admin
from app.core.email import Mailer, get_mailer
from app.db.models import User
from app.schemas.members import InviteIn, MemberOut, RoleIn
from app.services import members as svc

router = APIRouter(prefix="/organization/members", tags=["members"])
Admin = Annotated[User, Depends(require_admin)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


@router.get("")
def list_members(db: ScopedDb, ctx: CurrentAuth) -> list[MemberOut]:
    return svc.list_members(db, ctx.user)


@router.post("", status_code=201)
def invite(
    data: InviteIn, db: ScopedDb, ctx: CurrentAuth, admin: Admin, mailer: MailerDep
) -> MemberOut:
    user = svc.invite(db, admin, ctx.org, data, mailer)
    return next(m for m in svc.list_members(db, admin) if m.id == user.id)


@router.post("/{user_id}/resend", status_code=204)
def resend(
    user_id: uuid.UUID, db: ScopedDb, ctx: CurrentAuth, admin: Admin, mailer: MailerDep
) -> Response:
    svc.resend(db, admin, ctx.org, user_id, mailer)
    return Response(status_code=204)


@router.patch("/{user_id}")
def change_role(user_id: uuid.UUID, data: RoleIn, db: ScopedDb, admin: Admin) -> MemberOut:
    user = svc.change_role(db, admin, user_id, data.role)
    return next(m for m in svc.list_members(db, admin) if m.id == user.id)


@router.delete("/{user_id}", status_code=204)
def remove(user_id: uuid.UUID, db: ScopedDb, admin: Admin) -> Response:
    svc.remove(db, admin, user_id)
    return Response(status_code=204)
