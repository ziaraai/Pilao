import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin

EMBEDDING_DIM = get_settings().embedding_dim
DOCUMENT_KINDS = ("memoir_template", "past_memoir", "qse_policy", "technical_sheet", "other")
DOCUMENT_STATUSES = ("pending", "processing", "ready", "error")


class KnowledgeDocument(IdMixin, TimestampMixin, OrgScoped, Base):
    """A document the company deposited to feed its memoirs (US-1.4)."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            "kind in ('memoir_template','past_memoir','qse_policy','technical_sheet','other')",
            name="kind",
        ),
        CheckConstraint("status in ('pending','processing','ready','error')", name="status"),
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DocumentChunk(IdMixin, OrgScoped, Base):
    """Indexed passage. ``source_id`` points to a knowledge document or a DCE file."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("source_type in ('knowledge','dce')", name="source_type"),
        Index("ix_document_chunks_org_id_source", "org_id", "source_type", "source_id"),
        Index("ix_document_chunks_org_id_content_hash", "org_id", "content_hash"),
    )

    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int | None] = mapped_column(SmallInteger)
    page_to: Mapped[int | None] = mapped_column(SmallInteger)
    heading: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM))
    # `metadata` is reserved by SQLAlchemy's declarative API: the column keeps the spec name.
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
