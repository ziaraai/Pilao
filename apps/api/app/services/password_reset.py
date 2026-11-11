"""« Mot de passe oublié ? » (US-1.6): a one-hour, single-use link to choose a new password.

The request always gets the same answer, whether the address has an account or not. A company
user who never created their access (invited, no password) gets a fresh invitation instead; a
suspended company gets nothing. Choosing the new password closes every other session, confirms
the address (the link reached it) and signs in.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Email, Mailer, send_quietly
from app.core.errors import ApiError
from app.core.security import hash_password, hash_token, new_token
from app.db.models import AuditLog, AuthToken, Organization, User, UserSession
from app.services import members
from app.services.auth import LINK_CAP_MESSAGE, open_session, too_many_links
from app.services.suspension import is_suspended, suspended_error

KIND = "password_reset"
INVALID = "Ce lien n'est plus valable. Demandez-en un nouveau."


def _now() -> datetime:
    return datetime.now(UTC)


def _reset_email(db: Session, user: User) -> Email:
    """Stage a new link; send the returned e-mail once it is committed."""
    s = get_settings()
    token = new_token()
    db.add(
        AuthToken(
            org_id=user.org_id,
            user_id=user.id,
            kind=KIND,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(minutes=s.password_reset_ttl_minutes),
        )
    )
    return Email(
        to=user.email,
        subject="Choisir un nouveau mot de passe Pilao",
        body=(
            "Bonjour,\n\nPour choisir un nouveau mot de passe, ouvrez ce lien (valable 1 heure) :\n"
            f"{s.app_base_url}/nouveau-mot-de-passe?token={token}\n\n"
            "Si vous n'avez rien demandé, ignorez ce message : votre mot de passe ne change pas.\n"
        ),
    )


def request_reset(db: Session, email: str, mailer: Mailer) -> None:
    """Public: always the same answer for the caller (no account enumeration)."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return
    org = db.get_one(Organization, user.org_id)
    if is_suspended(org):
        return  # nothing leaves for a suspended company
    if user.password_hash is None:
        members.reinvite(db, user, org, mailer)
        return
    if too_many_links(db, user.id, KIND):
        return  # silent cap: no mail-bombing
    message = _reset_email(db, user)
    db.commit()
    send_quietly(mailer, message)  # the same answer, mail server down or not


def send_reset_link(db: Session, user: User, org: Organization, mailer: Mailer) -> None:
    """Sent from the administration: the same e-mail, the cap said out loud."""
    if too_many_links(db, user.id, KIND):
        raise ApiError(429, "too_many_emails", LINK_CAP_MESSAGE)
    message = _reset_email(db, user)
    db.commit()
    mailer.send(message)


def _valid_link(db: Session, token: str, lock: bool = False) -> tuple[AuthToken, User]:
    query = select(AuthToken).where(
        AuthToken.token_hash == hash_token(token), AuthToken.kind == KIND
    )
    row = db.scalar(query.with_for_update() if lock else query)
    user = db.get(User, row.user_id) if row is not None else None
    if row is None or row.used_at is not None or row.expires_at < _now() or user is None:
        raise ApiError(410, "reset_invalid", INVALID)
    if is_suspended(db.get_one(Organization, user.org_id)):
        raise suspended_error()
    return row, user


def lookup(db: Session, token: str) -> str:
    return _valid_link(db, token)[1].email


def reset(
    db: Session, token: str, password: str, ip: str | None, user_agent: str | None
) -> tuple[str, User]:
    row, user = _valid_link(db, token, lock=True)  # single use, even concurrently
    now = _now()
    row.used_at = now
    db.execute(  # the other links sent before stop working too
        update(AuthToken)
        .where(AuthToken.user_id == user.id, AuthToken.kind == KIND, AuthToken.used_at.is_(None))
        .values(used_at=now)
    )
    user.password_hash = hash_password(password)
    user.email_verified_at = user.email_verified_at or now  # the link reached this address
    for session in db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ):
        session.revoked_at = now
    db.add(
        AuditLog(
            org_id=user.org_id,
            user_id=user.id,
            action="password_reset",
            entity="user",
            entity_id=user.id,
        )
    )
    return open_session(db, user, ip, user_agent), user
