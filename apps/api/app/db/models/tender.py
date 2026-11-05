import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID  # ARRAY with @> (contains)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin

NOTICE_TYPES = ("contract_notice", "correction", "award", "other")


class Tender(IdMixin, TimestampMixin, Base):
    """A public notice (BOAMP, TED). Global: public data, shared by every organization;
    what concerns one company lives in ``tender_matches``."""

    __tablename__ = "tenders"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_tenders_source_source_id"),
        CheckConstraint("source in ('boamp','ted')", name="source"),
        CheckConstraint(
            "notice_type in (" + ",".join(f"'{t}'" for t in NOTICE_TYPES) + ")",
            name="notice_type",
        ),
        Index("ix_tenders_cpv_codes", "cpv_codes", postgresql_using="gin"),
        Index("ix_tenders_departments", "departments", postgresql_using="gin"),
    )

    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    notice_type: Mapped[str] = mapped_column(Text, nullable=False, default="contract_notice")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    buyer_name: Mapped[str | None] = mapped_column(Text)
    buyer_siret: Mapped[str | None] = mapped_column(Text)
    procedure: Mapped[str | None] = mapped_column(Text)
    contract_nature: Mapped[str | None] = mapped_column(Text)  # services | works | supplies
    cpv_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    departments: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    nuts_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    estimated_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notice_url: Mapped[str | None] = mapped_column(Text)
    documents_url: Mapped[str | None] = mapped_column(Text)
    lots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # The same contract published on BOAMP and TED: the second one points to the first
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="SET NULL")
    )
    # Corrections received (date, what changed), newest last (US-2.1 CA2)
    corrections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)


class TenderMatch(IdMixin, TimestampMixin, OrgScoped, Base):
    """A notice that passed one company's pre-filter, with its score (US-2.2, US-2.3)."""

    __tablename__ = "tender_matches"
    __table_args__ = (
        UniqueConstraint("org_id", "tender_id", name="uq_tender_matches_org_id_tender_id"),
        CheckConstraint("status in ('new','tracked','dismissed')", name="status"),
        CheckConstraint("score is null or (score between 0 and 100)", name="score"),
    )

    tender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="new")
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)  # pre-filter
    score: Mapped[int | None] = mapped_column(SmallInteger)
    explanation: Mapped[str | None] = mapped_column(Text)
    relevant_lots: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    score_error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismiss_reason: Mapped[str | None] = mapped_column(Text)
    bid_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bids.id", ondelete="SET NULL")
    )
    # When the daily e-mail considered this match (US-2.4): each notice is sent once
    digested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(IdMixin, TimestampMixin, OrgScoped, Base):
    """What was already sent, so a job run twice never e-mails twice (digest, expiry, correction)."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("org_id", "kind", "key", name="uq_notifications_org_id_kind_key"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)  # digest | vault_expiry | correction
    key: Mapped[str] = mapped_column(Text, nullable=False)  # e.g. "2026-11-05" or "<doc id>:30"
    recipients: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
