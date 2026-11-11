"""Super admin access: activation link, sign-in, sign-out (US-6.1)."""

from fastapi import APIRouter, Request, Response

from app.core.admin_deps import AdminDb, CurrentAdmin
from app.core.config import get_settings
from app.core.net import client_ip
from app.core.ratelimit import SlidingWindowLimiter
from app.schemas.admin import (
    AdminLoginIn,
    AdminMeOut,
    SetupConfirmIn,
    SetupConfirmOut,
    SetupLookupIn,
    SetupLookupOut,
    SetupPasswordIn,
    SetupPasswordOut,
)
from app.schemas.auth import MessageOut
from app.services.admin import auth as svc

router = APIRouter(prefix="/admin/auth", tags=["admin"])
_limiter = SlidingWindowLimiter(max_calls=20, window_seconds=60)


def _throttle(request: Request) -> None:
    _limiter.check(client_ip(request) or "unknown")


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.admin_session_cookie_name,
        token,
        max_age=s.admin_session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.post("/setup/lookup")
def setup_lookup(data: SetupLookupIn, request: Request, db: AdminDb) -> SetupLookupOut:
    _throttle(request)
    return SetupLookupOut(email=svc.setup_lookup(db, data.token).email)


@router.post("/setup/password")
def setup_password(data: SetupPasswordIn, request: Request, db: AdminDb) -> SetupPasswordOut:
    _throttle(request)
    return svc.setup_password(db, data.token, data.password)


@router.post("/setup/confirm")
def setup_confirm(
    data: SetupConfirmIn, request: Request, response: Response, db: AdminDb
) -> SetupConfirmOut:
    _throttle(request)
    token, out = svc.setup_confirm(
        db, data.token, data.code, client_ip(request), request.headers.get("user-agent")
    )
    _set_cookie(response, token)
    return out


@router.post("/login")
def login(data: AdminLoginIn, request: Request, response: Response, db: AdminDb) -> AdminMeOut:
    _throttle(request)
    token, admin = svc.login(
        db,
        data.email,
        data.password,
        data.code,
        client_ip(request),
        request.headers.get("user-agent"),
    )
    _set_cookie(response, token)
    return svc.me_out(db, admin)


@router.post("/logout")
def logout(response: Response, db: AdminDb, ctx: CurrentAdmin) -> MessageOut:
    svc.logout(db, ctx.session)
    response.delete_cookie(get_settings().admin_session_cookie_name, path="/")
    return MessageOut(message="Déconnecté.")


@router.get("/me")
def me(db: AdminDb, ctx: CurrentAdmin) -> AdminMeOut:
    return svc.me_out(db, ctx.admin)
