import uuid
from datetime import datetime

from sqlalchemy import CHAR, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Organization(IdMixin, TimestampMixin, Base):
    """Tenant root. A scoped session only sees its own organization (app.core.tenancy)."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "dce_retrieval_mode is null or dce_retrieval_mode in ('identified','anonymous')",
            name="dce_retrieval_mode",
        ),
    )

    siren: Mapped[str] = mapped_column(CHAR(9), nullable=False, index=True)
    siret: Mapped[str] = mapped_column(CHAR(14), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    legal_form: Mapped[str | None] = mapped_column(Text)
    naf_code: Mapped[str | None] = mapped_column(String(10))
    address_line: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(10))
    city: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(CHAR(3))
    headcount_range: Mapped[str | None] = mapped_column(Text)
    logo_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    brand_color: Mapped[str | None] = mapped_column(String(9))
    # Used to pre-fill DC1/DC2 (US-4.5): entered once by the company, never guessed
    phone: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    signatory_name: Mapped[str | None] = mapped_column(Text)
    signatory_role: Mapped[str | None] = mapped_column(Text)
    # Set by the platform administration (lot 2): nobody of the company gets in, nothing leaves
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[str | None] = mapped_column(Text)
    # The modules the company has (lot 3, app/modules.py): both by default
    modules: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{veille,reponse}",
        default=lambda: ["veille", "reponse"],
    )
    # Its plan (lot 4): the modules it gives and its credits; never left empty
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    welcome_credits_at: Mapped[datetime | None] = mapped_column(  # welcome credits: given once
        DateTime(timezone=True)
    )
    # DCE retrieval: on the company's behalf or anonymously (None = ask), and the contact
    # given to the buyers' platforms when on its behalf
    dce_retrieval_mode: Mapped[str | None] = mapped_column(Text)
    buyer_contact_first_name: Mapped[str | None] = mapped_column(Text)
    buyer_contact_last_name: Mapped[str | None] = mapped_column(Text)
    buyer_contact_email: Mapped[str | None] = mapped_column(Text)
