"""The platform's own tables (back-office): global, never tied to a company's ``org_id`` scope.

A super admin is not a company user: separate accounts, separate sessions, separate cookie
(ADR-040). Nothing here is reachable from a company session.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


def _now() -> datetime:
    return datetime.now(UTC)


class PlatformAdmin(IdMixin, TimestampMixin, Base):
    """A super admin. Created and reset only by ``python -m app.cli admin-access``."""

    __tablename__ = "platform_admins"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    # The authenticator secret, encrypted (core.crypto); confirmed once a first code matched.
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)  # a code is used once
    recovery_codes: Mapped[list[str]] = mapped_column(  # SHA-256 of the codes still unused
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    setup_token_hash: Mapped[str | None] = mapped_column(CHAR(64), unique=True)
    setup_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformAdminSession(IdMixin, TimestampMixin, Base):
    """Server-side session of a super admin: ``user_sessions`` without an organization."""

    __tablename__ = "platform_admin_sessions"

    admin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("platform_admins.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)


class PlatformAuditLog(IdMixin, Base):
    """What the super admins did (and failed sign-ins, which the throttle counts).

    ``org_id`` has no foreign key on purpose: the line outlives the company it is about.
    """

    __tablename__ = "platform_audit_logs"
    __table_args__ = (Index("ix_platform_audit_logs_action_at", "action", "at"),)

    admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admins.id", ondelete="SET NULL")
    )
    admin_email: Mapped[str] = mapped_column(Text, nullable=False)  # the address typed, on failure
    action: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # Set by the application: Postgres' now() is frozen for a whole transaction.
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), nullable=False
    )
    ip: Mapped[str | None] = mapped_column(INET)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
