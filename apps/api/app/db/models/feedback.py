import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class Feedback(IdMixin, TimestampMixin, OrgScoped, Base):
    """What users tell us from inside the application (P4-02): an idea, a problem, a
    question, with the page it came from. Part of the company's data (export, erasure)."""

    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("kind in ('idea','problem','question')", name="kind"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[str | None] = mapped_column(Text)
    bid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="SET NULL")
    )
