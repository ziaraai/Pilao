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
    # none | pending | ready | error | stale (text edited since) — runs once all are drafted
    conformity_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="none", server_default="none"
    )
    conformity_error: Mapped[str | None] = mapped_column(Text)
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
    instruction: Mapped[str | None] = mapped_column(Text)  # free instruction for a regeneration
    generated_by_model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Number of the current revision (0 = never drafted); an edit must start from it
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class MemoirSectionRevision(IdMixin, TimestampMixin, OrgScoped, Base):
    """US-4.4 CA4: every text a chapter has had (drafted, edited, restored) is kept."""

    __tablename__ = "memoir_section_revisions"
    __table_args__ = (
        CheckConstraint("origin in ('generated','edited','restored')", name="origin"),
        UniqueConstraint(
            "section_id", "revision", name="uq_memoir_section_revisions_section_id_revision"
        ),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memoir_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    covered_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    instruction: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ConformityItem(IdMixin, TimestampMixin, OrgScoped, Base):
    """US-4.3: one row per CCTP requirement and memoir version."""

    __tablename__ = "conformity_items"
    __table_args__ = (
        CheckConstraint("status in ('covered','partial','missing')", name="status"),
        UniqueConstraint(
            "memoir_id", "requirement_id", name="uq_conformity_items_memoir_id_requirement_id"
        ),
    )

    memoir_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memoirs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memoir_sections.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="ai")  # ai | declared
