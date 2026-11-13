import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped


def _now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


class DceFetch(IdMixin, OrgScoped, Base):
    """One attempt of the robot for a dossier (spec « Récupération des DCE », § 6): a retrieval
    asked by a user, an update found by the daily watch, or one daily check."""

    __tablename__ = "dce_fetches"
    __table_args__ = (
        CheckConstraint("kind in ('retrieval','update','check')", name="kind"),
        CheckConstraint("status in ('pending','running','done','error')", name="status"),
        CheckConstraint("mode is null or mode in ('identified','anonymous')", name="mode"),
        Index("ix_dce_fetches_bid_created", "bid_id", text("created_at DESC")),
        Index("ix_dce_fetches_status_created", "status", "created_at"),
        # one retrieval or update at a time per dossier, even when two requests race
        Index(
            "uq_dce_fetches_one_active_per_bid",
            "bid_id",
            unique=True,
            postgresql_where=text(
                "status in ('pending','running') and kind in ('retrieval','update')"
            ),
        ),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    outcome: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)  # shown as is
    site: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)  # the link this attempt was for
    size_label: Mapped[str | None] = mapped_column(Text)
    dce_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_versions.id", ondelete="SET NULL")
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
