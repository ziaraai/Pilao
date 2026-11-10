"""Retention of security data (privacy policy, docs/09): nothing is kept longer than needed.

Run every hour with the alerts (unscoped session):

* ``login_attempts`` after ``LOGIN_ATTEMPTS_RETENTION_DAYS`` (30): enough to investigate an
  attack, while the throttle itself only looks at the last 15 minutes;
* sessions once expired or ended (logout);
* single-use links once used or expired. The resend cap counts the links of the last hour
  of an unverified account: those are neither used (unverified) nor expired (48 h);
* super admin sessions once expired or ended, and the platform audit log after
  ``ADMIN_AUDIT_RETENTION_DAYS`` (365).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Delete, delete, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AuthToken,
    LoginAttempt,
    PlatformAdminSession,
    PlatformAuditLog,
    UserSession,
)

logger = logging.getLogger("pilao.retention")


@dataclass
class RetentionReport:
    login_attempts: int = 0
    sessions: int = 0
    tokens: int = 0
    admin_sessions: int = 0
    admin_audit: int = 0


def _deleted(db: Session, statement: Delete) -> int:
    return int(db.execute(statement).rowcount)  # type: ignore[attr-defined]


def purge_expired(db: Session, now: datetime | None = None) -> RetentionReport:
    now = now or datetime.now(UTC)
    keep = timedelta(days=get_settings().login_attempts_retention_days)
    report = RetentionReport(
        login_attempts=_deleted(db, delete(LoginAttempt).where(LoginAttempt.at < now - keep)),
        sessions=_deleted(
            db,
            delete(UserSession).where(
                or_(UserSession.expires_at < now, UserSession.revoked_at.is_not(None))
            ),
        ),
        tokens=_deleted(
            db,
            delete(AuthToken).where(
                or_(AuthToken.expires_at < now, AuthToken.used_at.is_not(None))
            ),
        ),
        admin_sessions=_deleted(
            db,
            delete(PlatformAdminSession).where(
                or_(
                    PlatformAdminSession.expires_at < now,
                    PlatformAdminSession.revoked_at.is_not(None),
                )
            ),
        ),
        admin_audit=_deleted(
            db,
            delete(PlatformAuditLog).where(
                PlatformAuditLog.at
                < now - timedelta(days=get_settings().admin_audit_retention_days)
            ),
        ),
    )
    db.commit()
    if any(vars(report).values()):
        logger.info("retention: %s", report)
    return report
