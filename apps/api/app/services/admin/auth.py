"""Super admin sign-in: activation link, password + authenticator code, sessions (US-6.1).

A refusal never says which of the three (address, password, code) is wrong, and a wrong
password never consumes a code.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    verify_password,
)
from app.db.models import PlatformAdmin, PlatformAdminSession, PlatformAuditLog
from app.domain import totp
from app.schemas.admin import AdminMeOut, SetupConfirmOut, SetupPasswordOut
from app.services.admin import audit

SIGN_INS = ("login", "setup_completed")  # the entries that opened a session


def _now() -> datetime:
    return datetime.now(UTC)


def _refused() -> ApiError:
    return ApiError(401, "invalid_credentials", "Identifiants ou code incorrects.")


def _pending(db: Session, token: str) -> PlatformAdmin:
    """The account an activation link belongs to, while the link is valid."""
    admin = db.scalar(
        select(PlatformAdmin).where(PlatformAdmin.setup_token_hash == hash_token(token))
    )
    if (
        admin is None
        or admin.disabled_at is not None
        or admin.setup_expires_at is None
        or admin.setup_expires_at <= _now()
    ):
        raise ApiError(
            404,
            "invalid_setup_link",
            "Lien invalide ou expiré. Relancez la commande sur le serveur.",
        )
    return admin


def setup_lookup(db: Session, token: str) -> PlatformAdmin:
    return _pending(db, token)


def setup_password(db: Session, token: str, password: str) -> SetupPasswordOut:
    """Step 1 of the activation. Called again (page reloaded): a new secret replaces the old."""
    admin = _pending(db, token)
    secret = totp.new_secret()
    admin.password_hash = hash_password(password)
    admin.totp_secret_enc = crypto.encrypt(secret, totp.PURPOSE)
    admin.totp_confirmed_at = admin.totp_last_step = None
    db.commit()
    uri = totp.provisioning_uri(secret, admin.email)
    return SetupPasswordOut(secret=secret, otpauth_uri=uri, qr_svg=totp.qr_svg(uri))


def _fresh_step(admin: PlatformAdmin, code: str, now: datetime) -> int | None:
    """The time step ``code`` belongs to, if it is valid and was not used yet."""
    if not admin.totp_secret_enc:
        return None
    try:
        secret = crypto.decrypt(admin.totp_secret_enc, totp.PURPOSE)
    except crypto.DecryptError:  # APP_SECRET_KEY changed: the access must be reset
        return None
    step = totp.matching_step(secret, code, now)
    if step is None or (admin.totp_last_step is not None and step <= admin.totp_last_step):
        return None
    return step


def _open_session(
    db: Session, admin: PlatformAdmin, ip: str | None, user_agent: str | None, now: datetime
) -> str:
    token = new_token()
    db.add(
        PlatformAdminSession(
            admin_id=admin.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(hours=get_settings().admin_session_ttl_hours),
            user_agent=(user_agent or "")[:500] or None,
            ip=ip,
        )
    )
    admin.last_login_at = now
    return token


def setup_confirm(
    db: Session, token: str, code: str, ip: str | None, user_agent: str | None
) -> tuple[str, SetupConfirmOut]:
    """Step 2: a first right code activates the account and signs in. Returns the session
    token and, once, the recovery codes."""
    admin = _pending(db, token)
    now = _now()
    step = _fresh_step(admin, code, now) if admin.password_hash else None
    if step is None:
        raise ApiError(400, "invalid_code", "Code incorrect. Vérifiez l'heure de votre téléphone.")
    codes = totp.new_recovery_codes()
    admin.totp_confirmed_at, admin.totp_last_step = now, step
    admin.recovery_codes = [hash_token(c) for c in codes]
    admin.setup_token_hash = admin.setup_expires_at = None
    audit.record(db, "setup_completed", admin=admin, ip=ip, at=now)
    session_token = _open_session(db, admin, ip, user_agent, now)
    db.commit()
    return session_token, SetupConfirmOut(recovery_codes=codes, me=me_out(db, admin))


def _check_throttle(db: Session, email: str, ip: str | None, now: datetime) -> None:
    s = get_settings()
    failures = (
        select(func.count())
        .select_from(PlatformAuditLog)
        .where(
            PlatformAuditLog.action == "login_failed",
            PlatformAuditLog.at >= now - timedelta(minutes=s.login_window_minutes),
        )
    )
    per_email = db.scalar(failures.where(PlatformAuditLog.admin_email == email)) or 0
    per_ip = (db.scalar(failures.where(PlatformAuditLog.ip == ip)) or 0) if ip else 0
    if per_email >= s.admin_login_max_failures or per_ip >= s.login_max_failures_per_ip:
        raise ApiError(
            429, "too_many_attempts", "Trop de tentatives. Réessayez dans quelques minutes."
        )


def _consume_code(
    db: Session, admin: PlatformAdmin, code: str, ip: str | None, now: datetime
) -> bool:
    """An authenticator code (each time step once) or a recovery code (each once)."""
    step = _fresh_step(admin, code, now)
    if step is not None:
        admin.totp_last_step = step
        return True
    digest = hash_token(totp.normalize_recovery(code))
    if digest in admin.recovery_codes:
        admin.recovery_codes = [c for c in admin.recovery_codes if c != digest]
        audit.record(
            db,
            "recovery_code_used",
            admin=admin,
            ip=ip,
            at=now,
            meta={"left": len(admin.recovery_codes)},
        )
        return True
    return False


def login(
    db: Session,
    email: str,
    password: str,
    code: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[str, PlatformAdmin]:
    email = email.strip().lower()
    now = _now()
    # Serialize attempts on the same e-mail (lock held until commit) so that concurrent
    # requests cannot all pass the throttle check before any failure is recorded.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"admin-login:{email}"))))
    _check_throttle(db, email, ip, now)
    admin = db.scalar(select(PlatformAdmin).where(PlatformAdmin.email == email))
    # Always verified (against a dummy hash when unknown): timing does not tell accounts apart.
    ok = verify_password(admin.password_hash if admin else None, password)
    usable = admin is not None and admin.totp_confirmed_at is not None and admin.disabled_at is None
    if not (ok and usable and admin is not None and _consume_code(db, admin, code, ip, now)):
        audit.record(db, "login_failed", admin=admin, email=email, ip=ip, at=now)
        db.commit()
        raise _refused()
    if admin.password_hash and needs_rehash(admin.password_hash):
        admin.password_hash = hash_password(password)
    token = _open_session(db, admin, ip, user_agent, now)
    audit.record(db, "login", admin=admin, ip=ip, at=now)
    db.commit()
    return token, admin


def session_context(db: Session, token: str) -> tuple[PlatformAdmin, PlatformAdminSession] | None:
    """The super admin and session behind a cookie token, if still valid."""
    session = db.scalar(
        select(PlatformAdminSession).where(
            PlatformAdminSession.token_hash == hash_token(token),
            PlatformAdminSession.revoked_at.is_(None),
            PlatformAdminSession.expires_at > _now(),
        )
    )
    if session is None:
        return None
    admin = db.get(PlatformAdmin, session.admin_id)
    if admin is None or admin.disabled_at is not None:
        return None
    return admin, session


def logout(db: Session, session: PlatformAdminSession) -> None:
    if session.revoked_at is None:
        now = _now()
        session.revoked_at = now
        audit.record(db, "logout", admin=db.get(PlatformAdmin, session.admin_id), ip=None, at=now)
        db.commit()


def me_out(db: Session, admin: PlatformAdmin) -> AdminMeOut:
    sign_ins = db.scalars(
        select(PlatformAuditLog.at)
        .where(PlatformAuditLog.admin_id == admin.id, PlatformAuditLog.action.in_(SIGN_INS))
        .order_by(PlatformAuditLog.at.desc())
        .limit(2)
    ).all()
    return AdminMeOut(
        email=admin.email,
        full_name=admin.full_name,
        recovery_codes_left=len(admin.recovery_codes),
        previous_login_at=sign_ins[1] if len(sign_ins) == 2 else None,
    )
