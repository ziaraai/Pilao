import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin

DOCUMENT_KINDS = (
    "dc1",
    "dc2",
    "staff_list",
    "equipment_list",
    "references_list",
    "planning",
    "memoir_docx",
    "memoir_pdf",
    "bundle_zip",
)


class GeneratedDocument(IdMixin, TimestampMixin, OrgScoped, Base):
    """A document Pilao produced for a bid (US-4.5 pre-filled forms, US-4.6 exports)."""

    __tablename__ = "generated_documents"
    __table_args__ = (
        CheckConstraint(
            "kind in (" + ",".join(f"'{k}'" for k in DOCUMENT_KINDS) + ")", name="kind"
        ),
        CheckConstraint("status in ('pending','ready','error')", name="status"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False, index=True
    )
    memoir_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memoirs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    # What the company still has to fill in, as written in the document ([À COMPLÉTER : …])
    to_complete: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # What the user accepted to export anyway (US-4.6 CA4)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
