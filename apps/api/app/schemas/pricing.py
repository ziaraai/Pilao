"""Chiffrage (ADR-049): the company's rates and the price files of a dossier."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class RatesIn(BaseModel):
    """Empty fields are allowed: a missing rate leaves the prices that need it to fill."""

    hourly_rate_cents: int | None = Field(default=None, gt=0, le=100_000)
    night_pct: int | None = Field(default=None, ge=0, le=300)
    sunday_pct: int | None = Field(default=None, ge=0, le=300)
    holiday_pct: int | None = Field(default=None, ge=0, le=300)


class RatesOut(RatesIn):
    pass


class PriceLineOut(BaseModel):
    id: str
    section: str
    label: str
    unit: str
    quantity: str | None
    hourly: bool
    surcharge: Literal["none", "night", "sunday", "holiday"]
    option: bool  # an option or PSE: priced, out of the total
    hours: str | None
    price_cents: int | None
    total_cents: int | None
    source: Literal["hours", "price", "hourly", "none"]


class PriceSheetOut(BaseModel):
    id: uuid.UUID
    status: Literal["reading", "ready", "error"]
    error: str | None
    warnings: list[str]
    notes: list[str]
    rate_cents: int | None  # this dossier's rate (None: the company's)
    lines: list[PriceLineOut]
    total_cents: int  # the offer, options left out
    options_total_cents: int
    missing_count: int


class PriceFileOut(BaseModel):
    dce_file_id: uuid.UUID
    path: str
    kind: str
    fillable: bool  # an Excel (or .xls / .ods) file; a PDF cannot be filled
    sheet: PriceSheetOut | None


class PricesOut(BaseModel):
    rates: RatesOut
    files: list[PriceFileOut]


class EntryIn(BaseModel):
    """One line: hours (price = hours × rate) or a price typed directly; both null clears."""

    hours: str | None = Field(default=None, max_length=20)
    price_cents: int | None = Field(default=None, ge=0, le=10_000_000_000)


class SheetUpdateIn(BaseModel):
    entries: dict[str, EntryIn] = Field(default_factory=dict, max_length=500)
    rate_cents: int | None = Field(default=None, gt=0, le=100_000)
    set_rate: bool = False  # true: ``rate_cents`` replaces this dossier's rate (null: company's)
