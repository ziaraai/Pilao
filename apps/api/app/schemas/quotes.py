"""The company's quote for a consultation (ADR-052)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator


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


QuoteNumber = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]


class QuoteIn(BaseModel):
    summarize: bool = True  # read the CCTP again (paid) — else only rebuild the files (free)
    number: QuoteNumber | None = None  # the company's own number; empty: Pilao's (25/11)


class QuoteSettingsIn(BaseModel):
    validity_days: int | None = Field(default=None, ge=1, le=365)
    vat_bp: int | None = Field(default=None, ge=0, le=10_000)  # 2000 = 20 %
    inclusions: list[InclusionItem] | None = Field(default=None, max_length=20)
    number: QuoteNumber | None = None  # "" goes back to Pilao's number


class QuoteOut(BaseModel):
    id: uuid.UUID
    number: str
    proposed_number: str  # Pilao's D-AAAA-NNNN, shown when the field is emptied
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


class ConsultationPriceFileOut(BaseModel):
    dce_file_id: uuid.UUID
    path: str
    reason: str = ""


class ConsultationReadStateOut(BaseModel):
    """The reading of a consultation's documents (25/11): « none » before the first one."""

    status: Literal["none", "reading", "ready", "error", "waiting_credits"]
    error: str | None = None
    found: list[str] = []  # the facts read in the documents (their names)
    price_files: list[ConsultationPriceFileOut] = []  # the documents of quantities proposed
    updated_at: datetime | None = None
