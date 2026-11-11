"""FastAPI dependencies: current user / organization and the tenant-scoped session.

Every business router must obtain its DB session through :func:`get_scoped_db` (or
depend on :func:`get_current_org`). That is what guarantees multi-tenant isolation.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import hash_token
from app.core.tenancy import scope_session
from app.db.models import Organization, User, UserSession
from app.db.session import get_db
from app.services.suspension import is_suspended, suspended_error

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class AuthContext:
    user: User
    org: Organization
    session: UserSession


def _csrf_check(request: Request) -> None:
    """Cookie auth => unsafe requests must come from our own origin (browsers send Origin)."""
    if request.method in SAFE_METHODS:
        return
    allowed = urlsplit(get_settings().app_base_url)
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        o = urlsplit(origin)
        if (o.scheme, o.netloc) == (allowed.scheme, allowed.netloc):
            return
    raise ApiError(403, "csrf", "Origine de la requête non autorisée.")


def get_auth_context(request: Request, db: Annotated[Session, Depends(get_db)]) -> AuthContext:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise ApiError(401, "not_authenticated", "Connexion requise.")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None:
        raise ApiError(401, "not_authenticated", "Connexion requise.")
    _csrf_check(request)
    user = db.get_one(User, session.user_id)
    org = db.get_one(Organization, user.org_id)
    if is_suspended(org):
        raise suspended_error()
    # From here on, the session only sees (and may only write) this organization's rows.
    scope_session(db, org.id)
    return AuthContext(user=user, org=org, session=session)


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]


def get_current_user(ctx: CurrentAuth) -> User:
    return ctx.user


def get_current_org(ctx: CurrentAuth) -> Organization:
    return ctx.org


def require_admin(ctx: CurrentAuth) -> User:
    if ctx.user.role != "org_admin":
        raise ApiError(403, "forbidden", "Réservé aux administrateurs de l'organisation.")
    return ctx.user


def get_scoped_db(_: CurrentAuth, db: Annotated[Session, Depends(get_db)]) -> Session:
    """The request's DB session, already scoped to the caller's organization."""
    return db


ScopedDb = Annotated[Session, Depends(get_scoped_db)]
