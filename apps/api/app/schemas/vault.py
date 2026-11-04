import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.domain.vault import DATE_REQUIRED

Kind = Literal[
    "kbis",
    "rne_certificate",
    "urssaf_vigilance",
    "tax_compliance",
    "cibtp_certificate",
    "insurance_rc_pro",
    "insurance_decennale",
    "qualification",
    "other",
]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


def _siren(value: str) -> str:
    digits = re.sub(r"[\s.]", "", value)
    if not re.fullmatch(r"\d{9}", digits):
        raise ValueError("SIREN invalide (9 chiffres)")
    return digits


Siren = Annotated[str, AfterValidator(_siren)]


class ReadingOut(BaseModel):
    """What the model must return (docs/prompts/lecture_attestation.md). Lenient on purpose:
    anything unreadable is None and is validated by the user at confirmation time."""

    kind: Kind = "other"
    issuer: str | None = None
    holder_name: str | None = None
    siren_on_document: str | None = None
    issued_at: date | None = None
    valid_until: date | None = None
    validity_rule: Literal["written", "urssaf_6_months", "kbis_3_months"] | None = None
    verification_code: str | None = None
    confidence: float | None = None

    @field_validator("siren_on_document", mode="before")
    @classmethod
    def _lenient_siren(cls, v: object) -> str | None:
        digits = re.sub(r"\D", "", str(v)) if v is not None else ""
        return digits if len(digits) == 9 else (digits[:9] if len(digits) == 14 else None)

    @field_validator("issuer", "holder_name", "verification_code", mode="before")
    @classmethod
    def _text(cls, v: object) -> str | None:
        return str(v).strip()[:300] or None if v is not None else None

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, v: float | None) -> float | None:
        return None if v is None else max(0.0, min(1.0, v))


class ConfirmIn(BaseModel):
    kind: Kind
    issuer: Short | None = None
    siren_on_document: Siren | None = None
    issued_at: date | None = None
    valid_until: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> "ConfirmIn":
        if self.kind in DATE_REQUIRED and self.valid_until is None:
            raise ValueError("la date de fin de validité est obligatoire pour ce type de document")
        if self.issued_at and self.valid_until and self.valid_until < self.issued_at:
            raise ValueError("la date de fin précède la date de délivrance")
        return self


class ComplianceDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_id: uuid.UUID
    kind: Kind
    issuer: str | None
    holder_name: str | None
    siren_on_document: str | None
    issued_at: date | None
    valid_until: date | None
    validity_rule: str | None
    status: Literal["pending_review", "valid", "expiring", "expired", "mismatch"]
    days_left: int | None = None
    alerts: list[str] = Field(default_factory=list)
    reading_status: Literal["pending", "reading", "done", "error"]
    reading_error: str | None
    confirmed_at: datetime | None
    created_at: datetime


class HelpLinkOut(BaseModel):
    kind: str
    label: str
    url: str


class MissingOut(BaseModel):
    label: str
    kinds: list[str]


class SummaryOut(BaseModel):
    counts: dict[str, int]
    attention: list[ComplianceDocOut]
    missing: list[MissingOut]
