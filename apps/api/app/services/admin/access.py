"""Granting, resetting and closing a super admin access: only from the server (CLI).

No screen and no API route calls these: creating a platform administrator takes a shell on
the server (ADR-040).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.db.models import PlatformAdmin, PlatformAdminSession
from app.services.admin import audit


def _revoke_sessions(db: Session, admin: PlatformAdmin, now: datetime) -> None:
    db.execute(
        update(PlatformAdminSession)
        .where(PlatformAdminSession.admin_id == admin.id, PlatformAdminSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def _find(db: Session, email: str) -> PlatformAdmin | None:
    return db.scalar(select(PlatformAdmin).where(PlatformAdmin.email == email.strip().lower()))


def grant_access(db: Session, email: str, full_name: str | None = None) -> str:
    """Create the account, or reset its access; returns the one-time activation token."""
    now = datetime.now(UTC)
    admin = _find(db, email)
    if admin is None:
        admin = PlatformAdmin(email=email.strip().lower(), recovery_codes=[])
        db.add(admin)
    if full_name:
        admin.full_name = full_name
    admin.password_hash = admin.totp_secret_enc = None
    admin.totp_confirmed_at = admin.totp_last_step = admin.disabled_at = None
    admin.recovery_codes = []
    token = new_token()
    admin.setup_token_hash = hash_token(token)
    admin.setup_expires_at = now + timedelta(minutes=get_settings().admin_setup_ttl_minutes)
    db.flush()
    _revoke_sessions(db, admin, now)
    audit.record(db, "access_reset", admin=admin, meta={"by": "cli"}, at=now)
    db.commit()
    return token


def disable(db: Session, email: str) -> bool:
    """Close the account and its sessions at once. False when no such account exists."""
    now = datetime.now(UTC)
    admin = _find(db, email)
    if admin is None:
        return False
    admin.disabled_at = now
    admin.setup_token_hash = admin.setup_expires_at = None
    _revoke_sessions(db, admin, now)
    audit.record(db, "disabled", admin=admin, meta={"by": "cli"}, at=now)
    db.commit()
    return True
