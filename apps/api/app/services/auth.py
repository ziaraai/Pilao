import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Email, Mailer
from app.core.errors import ApiError
from app.core.security import hash_password, hash_token, needs_rehash, new_token, verify_password
from app.db.models import AuditLog, AuthToken, LoginAttempt, Organization, User, UserSession
from app.integrations.recherche_entreprises import CompanyDirectory, CompanyLookupUnavailable
from app.schemas.auth import RegisterIn

VERIFY_KIND = "email_verify"


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(db: Session, user: User, action: str, entity: str, entity_id: uuid.UUID | None) -> None:
    db.add(
        AuditLog(
            org_id=user.org_id, user_id=user.id, action=action, entity=entity, entity_id=entity_id
        )
    )


def _send_verification(db: Session, user: User, mailer: Mailer) -> None:
    s = get_settings()
    token = new_token()
    db.add(
        AuthToken(
            org_id=user.org_id,
            user_id=user.id,
            kind=VERIFY_KIND,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(hours=s.email_verify_ttl_hours),
        )
    )
    mailer.send(
        Email(
            to=user.email,
            subject="Confirmez votre adresse e-mail — Pilao",
            body=(
                "Bonjour,\n\nPour activer votre compte Pilao, ouvrez ce lien "
                f"(valable {s.email_verify_ttl_hours} h) :\n"
                f"{s.app_base_url}/verifier-email?token={token}\n"
            ),
        )
    )


def register(
    db: Session, data: RegisterIn, mailer: Mailer, directory: CompanyDirectory | None = None
) -> None:
    if db.scalar(select(Organization.id).where(Organization.siret == data.siret)):
        raise ApiError(409, "siret_taken", "Ce SIRET est déjà associé à un compte.")
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise ApiError(409, "email_taken", "Cette adresse e-mail est déjà utilisée.")
    org = Organization(siren=data.siret[:9], siret=data.siret, name=data.org_name)
    if directory is not None:  # best effort: the registry being down must never block sign-up
        try:
            info = directory.lookup_siret(data.siret)
        except CompanyLookupUnavailable:
            info = None
        if info is not None:
            org.legal_form, org.naf_code = info.legal_form, info.naf_code
            org.address_line, org.postal_code = info.address_line, info.postal_code
            org.city, org.department = info.city, info.department
            org.headcount_range = info.headcount_range
    try:
        db.add(org)
        db.flush()
        user = User(
            org_id=org.id,
            email=data.email,
            full_name=data.full_name,
            role="org_admin",
            password_hash=hash_password(data.password),
        )
        db.add(user)
        db.flush()
        _audit(db, user, "register", "user", user.id)
        _send_verification(db, user, mailer)
        db.commit()
    except IntegrityError:  # concurrent registration with the same SIRET / e-mail
        db.rollback()
        raise ApiError(409, "already_exists", "Ce compte existe déjà.") from None


def verify_email(db: Session, token: str) -> None:
    row = db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(token), AuthToken.kind == VERIFY_KIND
        )
    )
    if row is None or row.used_at is not None or row.expires_at < _now():
        raise ApiError(400, "invalid_token", "Lien invalide ou expiré.")
    user = db.get_one(User, row.user_id)
    row.used_at = _now()
    user.email_verified_at = user.email_verified_at or _now()
    _audit(db, user, "verify_email", "user", user.id)
    db.commit()


def resend_verification(db: Session, email: str, mailer: Mailer) -> None:
    """Always succeeds from the caller's point of view (no account enumeration)."""
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and user.email_verified_at is None:
        _send_verification(db, user, mailer)
        db.commit()


def _check_throttle(db: Session, email: str, ip: str | None) -> None:
    s = get_settings()
    since = _now() - timedelta(minutes=s.login_window_minutes)
    failures = (
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.success.is_(False), LoginAttempt.at >= since)
    )
    per_email = db.scalar(failures.where(LoginAttempt.email == email)) or 0
    per_ip = db.scalar(failures.where(LoginAttempt.ip == ip)) if ip else 0
    if per_email >= s.login_max_failures_per_email or (per_ip or 0) >= s.login_max_failures_per_ip:
        raise ApiError(
            429, "too_many_attempts", "Trop de tentatives. Réessayez dans quelques minutes."
        )


def login(
    db: Session, email: str, password: str, ip: str | None, user_agent: str | None
) -> tuple[str, User]:
    email = email.lower()
    _check_throttle(db, email, ip)
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else None, password)
    db.add(LoginAttempt(email=email, ip=ip, success=ok))
    if not ok or user is None:
        db.commit()
        raise ApiError(401, "invalid_credentials", "E-mail ou mot de passe incorrect.")
    if user.email_verified_at is None:
        db.commit()
        raise ApiError(403, "email_not_verified", "Veuillez d'abord confirmer votre e-mail.")
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    token = new_token()
    session = UserSession(
        org_id=user.org_id,
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=_now() + timedelta(hours=get_settings().session_ttl_hours),
        user_agent=(user_agent or "")[:500] or None,
        ip=ip,
    )
    db.add(session)
    user.last_login_at = _now()
    db.flush()
    _audit(db, user, "login", "session", session.id)
    db.commit()
    return token, user


def logout(db: Session, token: str) -> None:
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is not None and session.revoked_at is None:
        session.revoked_at = _now()
        db.commit()
