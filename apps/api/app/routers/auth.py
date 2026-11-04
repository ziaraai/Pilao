import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import CurrentAuth
from app.core.email import Mailer, get_mailer
from app.db.models import Organization, User
from app.db.session import get_db
from app.schemas.auth import LoginIn, MeOut, MessageOut, OrgOut, RegisterIn, ResendIn, VerifyEmailIn
from app.services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])
Db = Annotated[Session, Depends(get_db)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


def _client_ip(request: Request) -> str | None:
    """Client IP if it is a valid address. Behind a proxy, run uvicorn with --proxy-headers."""
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


def _me_from(user: User, org: Organization) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        org=OrgOut(id=org.id, name=org.name, siret=org.siret),
    )


@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Db, mailer: MailerDep) -> MessageOut:
    svc.register(db, data, mailer)
    return MessageOut(message="Compte créé. Consultez votre e-mail pour le confirmer.")


@router.post("/verify-email")
def verify_email(data: VerifyEmailIn, db: Db) -> MessageOut:
    svc.verify_email(db, data.token)
    return MessageOut(message="Adresse e-mail confirmée. Vous pouvez vous connecter.")


@router.post("/resend-verification")
def resend(data: ResendIn, db: Db, mailer: MailerDep) -> MessageOut:
    svc.resend_verification(db, data.email, mailer)
    return MessageOut(message="Si un compte non confirmé existe, un e-mail vient d'être envoyé.")


@router.post("/login")
def login(data: LoginIn, request: Request, response: Response, db: Db) -> MeOut:
    ip = _client_ip(request)
    token, user = svc.login(db, data.email, data.password, ip, request.headers.get("user-agent"))
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return _me_from(user, db.get_one(Organization, user.org_id))


@router.post("/logout")
def logout(request: Request, response: Response, db: Db, _: CurrentAuth) -> MessageOut:
    s = get_settings()
    svc.logout(db, request.cookies[s.session_cookie_name])
    response.delete_cookie(s.session_cookie_name, path="/")
    return MessageOut(message="Déconnecté.")


@router.get("/me")
def me(ctx: CurrentAuth) -> MeOut:
    return _me_from(ctx.user, ctx.org)
