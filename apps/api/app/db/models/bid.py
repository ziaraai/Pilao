import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class Bid(IdMixin, TimestampMixin, OrgScoped, Base):
    """A response file ("dossier") for one tender, from review to result."""

    __tablename__ = "bids"
    __table_args__ = (
        CheckConstraint(
            "status in ('to_review','in_progress','submitted','won','lost','dropped')",
            name="status",
        ),
    )

    tender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_name: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(Text)  # the buyer's consultation reference
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="to_review")
    lot_label: Mapped[str | None] = mapped_column(Text)
    submitted_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    result_rank: Mapped[int | None] = mapped_column(Integer)
    result_notes: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class DceVersion(IdMixin, TimestampMixin, OrgScoped, Base):
    """One deposit of the DCE. A new deposit (modified DCE) is a new version (CA4)."""

    __tablename__ = "dce_versions"
    __table_args__ = (
        UniqueConstraint("bid_id", "version", name="uq_dce_versions_bid_id_version"),
        CheckConstraint("status in ('pending','processing','ready','error')", name="status"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    # Files exactly as deposited (ZIP or documents); members are in dce_files.
    source_file_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    skipped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    diff_summary: Mapped[str | None] = mapped_column(Text)


class DceFile(IdMixin, TimestampMixin, OrgScoped, Base):
    __tablename__ = "dce_files"
    __table_args__ = (
        CheckConstraint(
            "detected_kind in ('rc','ccap','cctp','ae','bpu','dpgf','dqe','annex','other')",
            name="detected_kind",
        ),
        CheckConstraint(
            "text_status in ('pending','ready','error','unsupported','ocr_unavailable')",
            name="text_status",
        ),
    )

    dce_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dce_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)  # path inside the deposit
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    detected_kind: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    kind_source: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    kind_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    text_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    text_error: Mapped[str | None] = mapped_column(Text)
    paginated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )


class DcePage(IdMixin, OrgScoped, Base):
    """Text of one page of a DCE piece: the unit every extracted fact cites (file + page)."""

    __tablename__ = "dce_pages"
    __table_args__ = (
        UniqueConstraint("dce_file_id", "page", name="uq_dce_pages_dce_file_id_page"),
    )

    dce_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_files.id", ondelete="CASCADE"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ocr_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
