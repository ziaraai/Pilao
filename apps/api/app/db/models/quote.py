"""The company's own quote for a consultation (ADR-052)."""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class Quote(IdMixin, TimestampMixin, OrgScoped, Base):
    """One quote per dossier, numbered per company and year (« D-2026-0001»)."""

    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("bid_id", name="uq_quotes_bid_id"),
        UniqueConstraint("org_id", "year", "seq", name="uq_quotes_org_id_year_seq"),
        CheckConstraint("status in ('drafting','ready','error')", name="status"),
        CheckConstraint("validity_days between 1 and 365", name="validity"),
        CheckConstraint("vat_bp between 0 and 10000", name="vat"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="drafting")
    error: Mapped[str | None] = mapped_column(Text)
    # what the CCTP asks for the rubriques priced, each with its source (file, page)
    inclusions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    vat_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)  # 20,00 %
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    docx_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    # the quote and the client's price file filled, together (made with the quote)
    zip_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    @property
    def number(self) -> str:
        return f"D-{self.year}-{self.seq:04d}"
