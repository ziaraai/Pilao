"""Chiffrage (ADR-049): the company's rates and each price file of a dossier."""

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class PricingRates(IdMixin, TimestampMixin, OrgScoped, Base):
    """The company's hourly rate and surcharges (one row per company, Profil)."""

    __tablename__ = "pricing_rates"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_pricing_rates_org_id"),
        CheckConstraint("hourly_rate_cents is null or hourly_rate_cents > 0", name="rate"),
    )

    hourly_rate_cents: Mapped[int | None] = mapped_column(Integer)
    night_pct: Mapped[int | None] = mapped_column(Integer)
    sunday_pct: Mapped[int | None] = mapped_column(Integer)
    holiday_pct: Mapped[int | None] = mapped_column(Integer)


class PriceSheet(IdMixin, TimestampMixin, OrgScoped, Base):
    """One price file of a dossier (BPU, DPGF, DQE): its lines and what the company typed."""

    __tablename__ = "price_sheets"
    __table_args__ = (
        UniqueConstraint("dce_file_id", name="uq_price_sheets_dce_file_id"),
        CheckConstraint("status in ('reading','ready','error')", name="status"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dce_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dce_files.id", ondelete="CASCADE"), nullable=False
    )
    # the .xlsx filled: the buyer's file, or its conversion from .xls / .ods
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    # the last filled copy handed out (replaced at each download)
    filled_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="reading")
    error: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    mirrors: Mapped[dict[str, list[str]]] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    entries: Mapped[dict[str, dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=dict)
    rate_cents: Mapped[int | None] = mapped_column(Integer)  # this dossier's hourly rate
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
