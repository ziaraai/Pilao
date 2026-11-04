from sqlalchemy import CHAR, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Organization(IdMixin, TimestampMixin, Base):
    """Tenant root. Not tenant-filtered itself."""

    __tablename__ = "organizations"

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
    logo_file_id: Mapped[str | None] = mapped_column(Text)
    brand_color: Mapped[str | None] = mapped_column(String(9))
