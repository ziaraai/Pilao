"""Plans and credits (lot 4, ADR-043).

``plans`` and ``credit_prices`` belong to the platform (no ``org_id``): the operator sets them
in the administration. ``credit_entries`` is a company's credits ledger; its balance is
computed (``app.domain.credits``), never stored.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    event,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin
from app.db.models.organization import Organization

CREDIT_KINDS = ("charge", "refund", "grant", "welcome")


def _now() -> datetime:
    return datetime.now(UTC)


class Plan(IdMixin, TimestampMixin, Base):
    """A plan: the modules it gives and its credits. Archived, never deleted."""

    __tablename__ = "plans"
    __table_args__ = (
        Index("uq_plans_name_lower", text("lower(name)"), unique=True),
        Index(
            "uq_plans_is_default", "is_default", unique=True, postgresql_where=text("is_default")
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    modules: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default="{}"
    )
    monthly_credits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    welcome_credits: Mapped[int] = mapped_column(  # given once, at the first attribution
        Integer, nullable=False, default=0, server_default="0"
    )
    price_note: Mapped[str] = mapped_column(  # the operator's price: never shown to a company
        Text, nullable=False, default="", server_default=""
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditPrice(Base):
    """The price set for one paid action; an action without a row has its registry price."""

    __tablename__ = "credit_prices"

    action: Mapped[str] = mapped_column(Text, primary_key=True)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
        onupdate=_now,
        server_default=func.now(),
    )


class CreditEntry(IdMixin, OrgScoped, Base):
    """One movement of a company's credits. A charge is negative; ``monthly`` and ``extra`` say
    where it was taken, ``month`` (Paris) which month's credits it used."""

    __tablename__ = "credit_entries"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('charge', 'refund', 'grant', 'welcome')", name="credit_entries_kind"
        ),
        Index("ix_credit_entries_org_at", "org_id", "at"),
        Index("ix_credit_entries_org_month", "org_id", "month"),
    )

    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now()
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str | None] = mapped_column(Text)
    monthly: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    extra: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    month: Mapped[date | None] = mapped_column(Date)
    bid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    platform_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admins.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    refund_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credit_entries.id", ondelete="CASCADE"), unique=True
    )


@event.listens_for(Organization, "before_insert")
def _default_plan(_mapper: Mapper[Organization], connection: Connection, org: Organization) -> None:
    """Every new company gets a plan: the default one when none was chosen."""
    if org.plan_id is None:
        org.plan_id = connection.scalar(select(Plan.id).where(Plan.is_default))
