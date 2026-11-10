"""FastAPI dependencies of the platform administration (``/admin``).

Separate from the company space on purpose (ADR-040): another cookie, another sessions
table. Nothing here reads ``pilao_session``, and ``core.deps`` never reads the admin cookie.

Supervision routes take :data:`AdminReadDb`: the same unscoped session, switched to a
read-only transaction, so that PostgreSQL itself refuses any write to a company's data.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import _csrf_check
from app.core.errors import ApiError
from app.db.models import PlatformAdmin, PlatformAdminSession
from app.db.session import get_db
from app.services.admin import auth

AdminDb = Annotated[Session, Depends(get_db)]  # unscoped, read-write: sign-in and audit only


@dataclass(frozen=True)
class AdminContext:
    admin: PlatformAdmin
    session: PlatformAdminSession


def get_admin_context(request: Request, db: AdminDb) -> AdminContext:
    token = request.cookies.get(get_settings().admin_session_cookie_name)
    found = auth.session_context(db, token) if token else None
    if found is None:
        raise ApiError(401, "not_authenticated", "Connexion requise.")
    _csrf_check(request)
    return AdminContext(admin=found[0], session=found[1])


CurrentAdmin = Annotated[AdminContext, Depends(get_admin_context)]


def read_only(db: Session) -> Session:
    """End the current transaction and start a read-only one (until the request ends)."""
    db.commit()
    db.execute(text("SET TRANSACTION READ ONLY"))
    return db


def get_admin_read_db(_: CurrentAdmin, db: AdminDb) -> Session:
    """The request's session once the super admin is known, in a read-only transaction."""
    return read_only(db)


AdminReadDb = Annotated[Session, Depends(get_admin_read_db)]
