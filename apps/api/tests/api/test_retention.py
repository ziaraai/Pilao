"""Security data is not kept past its retention (privacy policy, ADR-029)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    AuthToken,
    LoginAttempt,
    PlatformAdmin,
    PlatformAdminSession,
    PlatformAuditLog,
    UserSession,
)
from app.services.alerts import run_daily
from tests.api.helpers import PASSWORD, register_payload, signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


def count(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_the_hourly_run_purges_old_attempts_ended_sessions_and_used_links(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    now = datetime.now(UTC)
    active = signed_in_client(make_client, outbox, 1)  # its link is used, its session open
    gone = signed_in_client(make_client, outbox, 2)
    assert gone.post("/auth/logout").status_code in (200, 204)  # an ended session
    pending = make_client()  # an account still to confirm: its link must keep working
    assert pending.post("/auth/register", json=register_payload(3)).status_code == 201
    link = outbox.last_token()
    bad = {"email": "user1@example.fr", "password": "mauvais mot de passe"}
    assert make_client().post("/auth/login", json=bad).status_code == 401
    db.execute(update(LoginAttempt).values(at=now - timedelta(days=31)))  # all of them old
    db.add(LoginAttempt(email="recent@example.fr", ip=None, success=False, at=now))
    db.commit()
    before = (count(db, LoginAttempt), count(db, UserSession), count(db, AuthToken))
    assert before == (4, 2, 3)

    report = run_daily(db, outbox, now).retention
    assert (report.login_attempts, report.sessions, report.tokens) == (3, 1, 2)
    assert db.scalars(select(LoginAttempt.email)).all() == ["recent@example.fr"]
    assert active.get("/auth/me").status_code == 200  # the open session is kept
    assert pending.post("/auth/verify-email", json={"token": link}).status_code == 200
    login = {"email": "user3@example.fr", "password": PASSWORD}
    assert pending.post("/auth/login", json=login).status_code == 200

    later = now + timedelta(days=15)  # sessions last 14 days
    assert run_daily(db, outbox, later).retention.sessions == 2
    assert count(db, UserSession) == 0


def test_the_run_purges_ended_admin_sessions_and_audit_lines_past_a_year(db: Session) -> None:
    from app.services.retention import purge_expired

    now = datetime.now(UTC)
    admin = PlatformAdmin(email="admin@exemple.fr", recovery_codes=[])
    db.add(admin)
    db.flush()
    hour = timedelta(hours=1)
    live = PlatformAdminSession(admin_id=admin.id, token_hash="1" * 64, expires_at=now + hour)
    expired = PlatformAdminSession(admin_id=admin.id, token_hash="2" * 64, expires_at=now - hour)
    ended = PlatformAdminSession(
        admin_id=admin.id, token_hash="3" * 64, expires_at=now + hour, revoked_at=now
    )
    old = PlatformAuditLog(admin_email=admin.email, action="login", at=now - timedelta(days=366))
    kept = PlatformAuditLog(admin_email=admin.email, action="login", at=now - timedelta(days=364))
    db.add_all([live, expired, ended, old, kept])
    db.commit()

    report = purge_expired(db, now)

    assert (report.admin_sessions, report.admin_audit) == (2, 1)
    assert list(db.scalars(select(PlatformAdminSession.id))) == [live.id]
    assert list(db.scalars(select(PlatformAuditLog.id))) == [kept.id]
