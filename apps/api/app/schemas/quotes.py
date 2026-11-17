"""The company's quote for a consultation (ADR-052)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class InclusionItem(BaseModel):
    """One bullet of « Prestations comprises »: its CCTP page, or none when the company wrote it."""

    text: str = Field(min_length=1, max_length=400)
    file: str | None = Field(default=None, max_length=300)
    page: int | None = Field(default=None, ge=1, le=10_000)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("texte vide")
        return value.strip()


class QuoteIn(BaseModel):
    summarize: bool = True  # read the CCTP again (paid) — else only rebuild the files (free)


class QuoteSettingsIn(BaseModel):
    validity_days: int | None = Field(default=None, ge=1, le=365)
    vat_bp: int | None = Field(default=None, ge=0, le=10_000)  # 2000 = 20 %
    inclusions: list[InclusionItem] | None = Field(default=None, max_length=20)


class QuoteOut(BaseModel):
    id: uuid.UUID
    number: str
    status: Literal["drafting", "ready", "error"]
    error: str | None
    inclusions: list[InclusionItem]
    validity_days: int
    vat_bp: int
    total_ht_cents: int | None  # None: unit prices only
    vat_cents: int | None
    total_ttc_cents: int | None
    options_total_cents: int
    has_pdf: bool
    has_docx: bool
    stale: bool  # the prices changed since the files were made
    updated_at: datetime


class QuoteStateOut(BaseModel):
    quote: QuoteOut | None
    blocking: str | None  # why a quote cannot be prepared now
    cctp: bool  # a CCTP to read: « Prestations comprises » (paid)


class QuoteDownloadIn(BaseModel):
    format: Literal["pdf", "docx", "zip"]
