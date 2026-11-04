import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CHAR, CheckConstraint, Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class ComplianceDocument(IdMixin, TimestampMixin, OrgScoped, Base):
    """An administrative attestation (Kbis, URSSAF, insurance...). Dates are user-confirmed."""

    __tablename__ = "compliance_documents"
    __table_args__ = (
        CheckConstraint(
            "kind in ('kbis','rne_certificate','urssaf_vigilance','tax_compliance',"
            "'cibtp_certificate','insurance_rc_pro','insurance_decennale','qualification','other')",
            name="kind",
        ),
        CheckConstraint(
            "status in ('pending_review','valid','expiring','expired','mismatch')", name="status"
        ),
        CheckConstraint(
            "reading_status in ('pending','reading','done','error')", name="reading_status"
        ),
        Index("ix_compliance_documents_org_id_valid_until", "org_id", "valid_until"),
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    issuer: Mapped[str | None] = mapped_column(Text)
    holder_name: Mapped[str | None] = mapped_column(Text)
    siren_on_document: Mapped[str | None] = mapped_column(CHAR(9))
    verification_code: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    validity_rule: Mapped[str | None] = mapped_column(Text)
    # Last computed status; the API always re-derives it from the dates (see domain/vault.py).
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")
    extracted: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reading_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    reading_error: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
