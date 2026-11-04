from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OrgScoped, TimestampMixin


class User(IdMixin, TimestampMixin, OrgScoped, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('org_admin','org_member')", name="role"),)

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="org_member")
    password_hash: Mapped[str | None] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformAdmin(IdMixin, TimestampMixin, Base):
    """Global table (support / back-office)."""

    __tablename__ = "platform_admins"

    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
