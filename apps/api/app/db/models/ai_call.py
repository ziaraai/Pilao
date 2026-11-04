import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, OptionalOrgScoped, TimestampMixin


class AiCall(IdMixin, TimestampMixin, OptionalOrgScoped, Base):
    """One row per LLM call: task, model, tokens, cost, latency (see app/ai/llm.py)."""

    __tablename__ = "ai_calls"

    bid_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(10, 5), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text)
