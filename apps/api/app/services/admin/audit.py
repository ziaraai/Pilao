"""Audit log of the platform administrators (``platform_audit_logs``)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import PlatformAdmin, PlatformAuditLog


def record(
    db: Session,
    action: str,
    *,
    admin: PlatformAdmin | None = None,
    email: str | None = None,
    org_id: uuid.UUID | None = None,
    ip: str | None = None,
    meta: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> None:
    """Add one line; the caller commits. ``email``: the address typed, when no account matches."""
    entry = PlatformAuditLog(
        admin_id=admin.id if admin else None,
        admin_email=admin.email if admin else (email or "")[:320],
        action=action,
        org_id=org_id,
        ip=ip,
        meta=meta or {},
    )
    if at is not None:
        entry.at = at
    db.add(entry)
