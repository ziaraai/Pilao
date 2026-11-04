import uuid
from datetime import date

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class CompanyProfile(IdMixin, TimestampMixin, OrgScoped, Base):
    """One row per organization: watch settings + financials."""

    __tablename__ = "company_profiles"
    __table_args__ = (
        UniqueConstraint("org_id", name="uq_company_profiles_org_id"),
        CheckConstraint("min_score_alert between 0 and 100", name="min_score_alert"),
        CheckConstraint(
            "min_amount_cents is null or max_amount_cents is null "
            "or min_amount_cents <= max_amount_cents",
            name="amount_range",
        ),
    )

    trades: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    cpv_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    keywords_include: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    keywords_exclude: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    departments: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    max_distance_km: Mapped[int | None] = mapped_column(Integer)
    min_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    revenue_y1_cents: Mapped[int | None] = mapped_column(BigInteger)
    revenue_y2_cents: Mapped[int | None] = mapped_column(BigInteger)
    revenue_y3_cents: Mapped[int | None] = mapped_column(BigInteger)
    min_score_alert: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=60)
    completeness_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)


class HumanResource(IdMixin, TimestampMixin, OrgScoped, Base):
    __tablename__ = "human_resources"

    qualification: Mapped[str] = mapped_column(Text, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class Equipment(IdMixin, TimestampMixin, OrgScoped, Base):
    __tablename__ = "equipment"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int | None] = mapped_column(Integer)
    spec_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )


class Certification(IdMixin, TimestampMixin, OrgScoped, Base):
    __tablename__ = "certifications"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str | None] = mapped_column(Text)
    valid_until: Mapped[date | None] = mapped_column(Date)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL")
    )


class CompanyReference(IdMixin, TimestampMixin, OrgScoped, Base):
    """A past job ("référence"). The embedding column is added with the RAG migration (P1-07)."""

    __tablename__ = "company_references"
    __table_args__ = (
        CheckConstraint("client_type in ('public','private')", name="client_type"),
        CheckConstraint("year is null or year between 1950 and 2100", name="year"),
    )

    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    client_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    cpv_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    photo_file_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
