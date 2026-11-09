import uuid
from typing import Any

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class ProfileSuggestion(IdMixin, TimestampMixin, OrgScoped, Base):
    """A profile line proposed from one of the company's documents (US-1.6). It joins the
    profile only when the user accepts it."""

    __tablename__ = "profile_suggestions"
    __table_args__ = (
        CheckConstraint(
            "kind in ('human_resource','equipment','certification','reference')", name="kind"
        ),
        CheckConstraint("status in ('pending','accepted','dismissed')", name="status"),
        Index("ix_profile_suggestions_org_id_status", "org_id", "status"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    missing: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    page: Mapped[int | None] = mapped_column(SmallInteger)
    heading: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
