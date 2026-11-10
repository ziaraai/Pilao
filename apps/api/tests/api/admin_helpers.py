"""Helpers for the platform administration tests: an activated super admin, its codes."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AiCall,
    Bid,
    DceAnalysis,
    DceVersion,
    GeneratedDocument,
    Job,
    Memoir,
    MemoirSection,
    Organization,
)
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


# --- Company data written straight into the database (unscoped session) -----------------


def org_named(db: Session, name: str) -> Organization:
    return db.scalars(select(Organization).where(Organization.name == name)).one()


def seed_bid(db: Session, org_id: uuid.UUID, title: str = "Dossier", **fields: Any) -> Bid:
    bid = Bid(org_id=org_id, title=title, **fields)
    db.add(bid)
    db.flush()
    return bid


def seed_memoir(
    db: Session, bid: Bid, status: str = "ready", content: str = "Texte", **fields: Any
) -> Memoir:
    """A memoir with one chapter, and the DCE version and analysis it needs."""
    version = DceVersion(org_id=bid.org_id, bid_id=bid.id, version=1, status="ready")
    db.add(version)
    db.flush()
    analysis = DceAnalysis(
        org_id=bid.org_id, bid_id=bid.id, dce_version_id=version.id, status="ready"
    )
    db.add(analysis)
    db.flush()
    memoir = Memoir(
        org_id=bid.org_id,
        bid_id=bid.id,
        dce_analysis_id=analysis.id,
        version=1,
        status=status,
        outline_source="sector_default",
        **fields,
    )
    db.add(memoir)
    db.flush()
    db.add(
        MemoirSection(
            org_id=bid.org_id,
            memoir_id=memoir.id,
            position=1,
            title="Moyens humains",
            status="ready",
            content_md=content,
        )
    )
    db.flush()
    return memoir


def seed_export(db: Session, bid: Bid, kind: str = "memoir_docx", **fields: Any) -> None:
    db.add(GeneratedDocument(org_id=bid.org_id, bid_id=bid.id, kind=kind, status="ready", **fields))
    db.flush()


def seed_ai_call(
    db: Session, org_id: uuid.UUID | None, task: str, cost: str, **fields: Any
) -> None:
    values: dict[str, Any] = {"model": "fournisseur/modele", "success": True} | fields
    db.add(AiCall(org_id=org_id, task=task, cost_eur=Decimal(cost), **values))
    db.flush()


def seed_job(db: Session, org_id: uuid.UUID | None, kind: str, status: str, **fields: Any) -> None:
    db.add(Job(org_id=org_id, kind=kind, status=status, **fields))
    db.flush()
