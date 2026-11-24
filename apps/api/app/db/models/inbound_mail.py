import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class InboundMail(IdMixin, TimestampMixin, OrgScoped, Base):
    """An e-mail received on the company's DCE address (24/11): its pieces, filed in a dossier
    or waiting « À classer », or a platform's notice that the DCE changed. The e-mail itself is
    deleted from the mailbox once read; only what follows is kept."""

    __tablename__ = "inbound_mails"
    __table_args__ = (
        UniqueConstraint("org_id", "message_id", name="uq_inbound_mails_org_id_message_id"),
        CheckConstraint("kind in ('dce','notice')", name="kind"),
        CheckConstraint("status in ('to_sort','filed','ignored')", name="status"),
    )

    message_id: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="to_sort")
    # the dossier it went to, and the one Pilao suggests when it could not be sure
    bid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="SET NULL"), index=True
    )
    suggested_bid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="SET NULL")
    )
    # the attachments kept until they are filed (then copied into the DCE and removed here)
    file_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    attachment_names: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    skipped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    links: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(Text)
