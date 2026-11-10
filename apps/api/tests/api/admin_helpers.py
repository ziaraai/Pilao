"""Helpers for the platform administration tests: an activated super admin, its codes."""

from collections.abc import Callable
from datetime import UTC, datetime

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.admin.access import grant_access

ADMIN_EMAIL = "admin@pilao.test"
ADMIN_PASSWORD = "un-mot-de-passe-long"


def code(secret: str, offset_steps: int = 0, when: datetime | None = None) -> str:
    """The authenticator code of ``when`` (now by default), ``offset_steps`` steps later."""
    return pyotp.TOTP(secret).at(when or datetime.now(UTC), counter_offset=offset_steps)


def activate(
    client: TestClient, db: Session, email: str = ADMIN_EMAIL, when: datetime | None = None
) -> tuple[str, list[str]]:
    """Grant an access and go through the activation: ``client`` ends up signed in.

    Returns the authenticator secret and the recovery codes.
    """
    token = grant_access(db, email, "Admin")
    chosen = client.post(
        "/admin/auth/setup/password", json={"token": token, "password": ADMIN_PASSWORD}
    )
    assert chosen.status_code == 200, chosen.text
    secret = chosen.json()["secret"]
    done = client.post(
        "/admin/auth/setup/confirm", json={"token": token, "code": code(secret, when=when)}
    )
    assert done.status_code == 200, done.text
    return secret, done.json()["recovery_codes"]


def activated_admin(make_client: Callable[[], TestClient], db: Session) -> tuple[TestClient, str]:
    """A signed-in super admin client, and its authenticator secret."""
    client = make_client()
    secret, _ = activate(client, db)
    return client, secret
