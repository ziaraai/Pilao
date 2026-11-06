import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import CurrentAuth
from app.core.email import Mailer, get_mailer
from app.core.legal import TERMS_VERSION
from app.db.models import Organization, User
from app.db.session import get_db
from app.integrations.recherche_entreprises import CompanyDirectory, get_company_directory
from app.schemas.auth import (
    LoginIn,
    MeOut,
    MessageOut,
    OrgOut,
    RegisterIn,
    RegisterOut,
    ResendIn,
    VerifyEmailIn,
)
from app.schemas.members import AcceptInvitationIn, InvitationLookupIn, InvitationOut
from app.services import auth as svc
from app.services import members

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
        terms_current=user.terms_version == TERMS_VERSION,
    )


@router.post("/register", status_code=201)
def register(
    data: RegisterIn,
    db: Db,
    mailer: MailerDep,
    directory: Annotated[CompanyDirectory, Depends(get_company_directory)],
) -> RegisterOut:
    if svc.register(db, data, mailer, directory):
        return RegisterOut(
            message="Compte créé. Consultez votre e-mail pour le confirmer.", email_sent=True
        )
    return RegisterOut(
        message=(
            "Compte créé, mais l'e-mail de confirmation n'est pas parti. Demandez-en un "
            "nouveau depuis la page de connexion."
        ),
        email_sent=False,
    )


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
    _set_session_cookie(response, token)
    return _me_from(user, db.get_one(Organization, user.org_id))


def _set_session_cookie(response: Response, token: str) -> None:
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


@router.post("/invitations/lookup")
def invitation(data: InvitationLookupIn, db: Db) -> InvitationOut:
    """The token goes in the body, never in a URL that access logs would keep."""
    return members.lookup(db, data.token)


@router.post("/invitations/accept")
def accept_invitation(
    data: AcceptInvitationIn, request: Request, response: Response, db: Db
) -> MeOut:
    token, user = members.accept(db, data, _client_ip(request), request.headers.get("user-agent"))
    _set_session_cookie(response, token)
    return _me_from(user, db.get_one(Organization, user.org_id))


@router.post("/logout")
def logout(response: Response, db: Db, ctx: CurrentAuth) -> MessageOut:
    svc.logout(db, ctx.session)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return MessageOut(message="Déconnecté.")


@router.get("/me")
def me(ctx: CurrentAuth) -> MeOut:
    return _me_from(ctx.user, ctx.org)


@router.post("/accept-terms")
def accept_terms(db: Db, ctx: CurrentAuth) -> MeOut:
    """The current version of the terms, accepted again after a change (CGU art. 12)."""
    svc.accept_terms(db, ctx.user)
    return _me_from(ctx.user, ctx.org)
