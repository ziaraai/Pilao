import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OptionalOrgScoped, TimestampMixin

JOB_STATUSES = ("pending", "running", "done", "error")


class Job(IdMixin, TimestampMixin, OptionalOrgScoped, Base):
    """Visible status of a background job (RQ). Jobs must be idempotent."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status in ('pending','running','done','error')", name="status"),
        CheckConstraint("progress between 0 and 100", name="progress"),
        Index("ix_jobs_kind_ref_id", "kind", "ref_id"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
