"""Platform settings changed from the administration (lot 5, ADR-044).

One row per setting set by the operator; no row = the server's value (``Settings``). No
``org_id``: a setting of the platform, like ``plans``. A secret (the OpenRouter key) is stored
encrypted (``app.core.crypto``), with its last 4 characters in clear for the screen.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any | None] = mapped_column(JSONB)
    secret: Mapped[str | None] = mapped_column(Text)
    secret_last4: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admins.id", ondelete="SET NULL")
    )
