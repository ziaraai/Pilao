import uuid
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class Memoir(IdMixin, TimestampMixin, OrgScoped, Base):
    """One version of the technical memoir of a bid. Its chapters are ``memoir_sections``
    (they are the outline: there is no separate outline column)."""

    __tablename__ = "memoirs"
    __table_args__ = (
        UniqueConstraint("bid_id", "version", name="uq_memoirs_bid_id_version"),
        CheckConstraint("status in ('draft','generating','ready','exported')", name="status"),
        CheckConstraint(
            "outline_source in ('rc_imposed','org_template','sector_default')",
            name="outline_source",
        ),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dce_analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_analyses.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    outline_source: Mapped[str] = mapped_column(Text, nullable=False)
    max_pages: Mapped[int | None] = mapped_column(Integer)
    word_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reference_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    # Why each reference was proposed: [{id, score, reasons}]
    reference_scores: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class MemoirSection(IdMixin, TimestampMixin, OrgScoped, Base):
    __tablename__ = "memoir_sections"
    __table_args__ = (
        CheckConstraint("status in ('pending','generating','ready','error')", name="status"),
    )

    memoir_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memoirs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    criterion_ref: Mapped[str | None] = mapped_column(Text)  # sub-criterion it answers
    criterion_weight: Mapped[float | None] = mapped_column(Float)
    requirement_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    word_budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    content_md: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    covered_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    generated_by_model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
