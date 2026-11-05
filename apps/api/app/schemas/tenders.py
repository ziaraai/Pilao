"""Notices: the normalized format every source is converted to, and the API outputs."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

NoticeType = Literal["contract_notice", "correction", "award", "other"]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class LotIn(BaseModel):
    number: str | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    cpv_codes: list[str] = Field(default_factory=list)
    estimated_amount_eur: float | None = Field(default=None, ge=0)


class TenderIn(BaseModel):
    """One notice as a source importer (BOAMP, TED) hands it over."""

    source: Literal["boamp", "ted"]
    source_id: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    notice_type: NoticeType = "contract_notice"
    corrects: str | None = None  # source_id of the notice a correction modifies
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    description: Annotated[str, StringConstraints(max_length=20_000)] | None = None
    buyer_name: Short | None = None
    buyer_siret: Annotated[str, StringConstraints(pattern=r"^\d{14}$")] | None = None
    procedure: Short | None = None
    contract_nature: Literal["services", "works", "supplies"] | None = None
    cpv_codes: list[str] = Field(default_factory=list, max_length=100)
    departments: list[str] = Field(default_factory=list, max_length=101)
    nuts_codes: list[str] = Field(default_factory=list, max_length=100)
    estimated_amount_eur: float | None = Field(default=None, ge=0)
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    notice_url: Short | None = None
    documents_url: Short | None = None
    lots: list[LotIn] = Field(default_factory=list, max_length=200)
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cpv_codes")
    @classmethod
    def _cpv(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(c.split("-")[0].strip() for c in v if c.strip()))


class TenderScoreOut(BaseModel):
    """What the scoring model must return (lenient on form)."""

    score: int = Field(ge=0, le=100)
    explanation: str = Field(min_length=1)
    relevant_lots: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, v: object) -> object:
        if isinstance(v, int | float) and not isinstance(v, bool):
            return max(0, min(100, round(v)))
        return v

    @field_validator("explanation", mode="before")
    @classmethod
    def _explanation(cls, v: object) -> object:
        return v.strip()[:400] if isinstance(v, str) else v

    @field_validator("relevant_lots", mode="before")
    @classmethod
    def _lots(cls, v: object) -> list[str]:
        return [str(x)[:200] for x in v if str(x).strip()] if isinstance(v, list) else []


class TenderMatchOut(BaseModel):
    tender_id: uuid.UUID
    source: str
    title: str
    description: str | None
    buyer_name: str | None
    procedure: str | None
    contract_nature: str | None
    cpv_codes: list[str]
    departments: list[str]
    estimated_amount_cents: int | None
    published_at: datetime | None
    deadline_at: datetime | None
    notice_url: str | None
    documents_url: str | None
    lots: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    status: Literal["new", "tracked", "dismissed"]
    score: int | None
    explanation: str | None
    relevant_lots: list[str]
    reasons: list[str]
    score_error: str | None
    dismiss_reason: str | None
    bid_id: uuid.UUID | None


class TenderListOut(BaseModel):
    items: list[TenderMatchOut]
    total: int
    departments: list[str]  # available filter values among the company's notices
    procedures: list[str]


class DismissIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
