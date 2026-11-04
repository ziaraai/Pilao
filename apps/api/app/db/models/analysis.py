import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class DceAnalysis(IdMixin, TimestampMixin, OrgScoped, Base):
    """AI analysis sheet of one DCE version (US-3.2). ``data`` follows dce_analysis.schema."""

    __tablename__ = "dce_analyses"
    __table_args__ = (
        CheckConstraint("status in ('pending','processing','ready','error')", name="status"),
        Index("ix_dce_analyses_bid_id_created_at", "bid_id", "created_at"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False
    )
    dce_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Items dropped or fields cleared because their source could not be verified, etc.
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    go_no_go_score: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Requirement(IdMixin, TimestampMixin, OrgScoped, Base):
    """One numbered CCTP requirement, with its source (file + page)."""

    __tablename__ = "requirements"
    __table_args__ = (
        CheckConstraint(
            "category in ('frequency','surface','product','schedule','staff','equipment',"
            "'quality','safety','environment','reporting','other')",
            name="category",
        ),
        CheckConstraint("importance in ('mandatory','expected','nice_to_have')", name="importance"),
        Index("ix_requirements_dce_analysis_id_position", "dce_analysis_id", "position"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dce_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_analyses.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    ref: Mapped[str] = mapped_column(Text, nullable=False)  # CCTP-1, CCTP-2...
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[str] = mapped_column(Text, nullable=False)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_files.id", ondelete="SET NULL")
    )
    page: Mapped[int | None] = mapped_column(Integer)
