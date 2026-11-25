import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class ConsultationRead(IdMixin, TimestampMixin, OrgScoped, Base):
    """The reading of a consultation's documents (25/11): the client's facts put in the
    dossier and the documents that hold the quantities. Its credit also covers the reading of
    one price file (``PriceSheet.included``)."""

    __tablename__ = "consultation_reads"
    __table_args__ = (
        UniqueConstraint("bid_id", name="uq_consultation_reads_bid_id"),
        CheckConstraint("status in ('reading','ready','error','waiting_credits')", name="status"),
    )

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="reading")
    error: Mapped[str | None] = mapped_column(Text)
    # the facts found (their names), and the documents proposed as price files
    found: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    price_files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
