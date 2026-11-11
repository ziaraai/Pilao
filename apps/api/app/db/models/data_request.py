import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class DataRequest(IdMixin, TimestampMixin, OrgScoped, Base):
    """GDPR requests of an organization: a full export, or the deletion of everything."""

    __tablename__ = "data_requests"
    __table_args__ = (
        CheckConstraint("kind in ('export','deletion')", name="kind"),
        CheckConstraint("status in ('pending','ready','error','cancelled')", name="status"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # deletion date
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # A deletion scheduled by Pilao from the administration (``requested_by`` is then empty)
    platform_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admins.id", ondelete="SET NULL")
    )


class PurgeLog(IdMixin, TimestampMixin, Base):
    """Proof that an organization was erased. Global and without personal data: the
    organization's id (no foreign key: the row is gone), the date and what was removed."""

    __tablename__ = "purge_logs"

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
