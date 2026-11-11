import re
import uuid
from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.domain.trades import TRADES

DEPARTMENT_RE = re.compile(r"^(0[1-9]|[1-8]\d|9[0-5]|2[AB]|97[1-6]|98\d)$")
CPV_RE = re.compile(r"^\d{8}$")
MAX_ITEMS = 200


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _department(v: str) -> str:
    v = v.strip().upper()
    if not DEPARTMENT_RE.match(v):
        raise ValueError(f"département invalide : {v}")
    return v


def _cpv(v: str) -> str:
    v = v.strip().split("-")[0]  # tolerate the "90911200-3" form (check digit)
    if not CPV_RE.match(v):
        raise ValueError(f"code CPV invalide : {v}")
    return v


Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Department = Annotated[str, AfterValidator(_department)]
Cpv = Annotated[str, AfterValidator(_cpv)]
Cents = Annotated[int, Field(ge=0, le=10**13)]


class ProfileIn(BaseModel):
    trades: list[str] = Field(default_factory=list, max_length=20)
    cpv_codes: list[Cpv] = Field(default_factory=list, max_length=MAX_ITEMS)
    keywords_include: list[Keyword] = Field(default_factory=list, max_length=MAX_ITEMS)
    keywords_exclude: list[Keyword] = Field(default_factory=list, max_length=MAX_ITEMS)
    departments: list[Department] = Field(default_factory=list, max_length=101)
    max_distance_km: int | None = Field(default=None, ge=0, le=5000)
    min_amount_cents: Cents | None = None
    max_amount_cents: Cents | None = None
    revenue_y1_cents: Cents | None = None
    revenue_y2_cents: Cents | None = None
    revenue_y3_cents: Cents | None = None
    min_score_alert: int = Field(default=60, ge=0, le=100)
    # When true, CPV codes and keywords of the selected trades are merged in (US-1.2 CA1).
    apply_trade_defaults: bool = False

    @field_validator("trades")
    @classmethod
    def _trades(cls, v: list[str]) -> list[str]:
        unknown = [t for t in v if t not in TRADES]
        if unknown:
            raise ValueError(f"métier inconnu : {', '.join(unknown)}")
        return _dedupe(v)

    @field_validator("cpv_codes", "keywords_include", "keywords_exclude", "departments")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return _dedupe(v)

    @model_validator(mode="after")
    def _ranges(self) -> "ProfileIn":
        lo, hi = self.min_amount_cents, self.max_amount_cents
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("le montant minimum dépasse le montant maximum")
        overlap = {k.lower() for k in self.keywords_include} & {
            k.lower() for k in self.keywords_exclude
        }
        if overlap:
            raise ValueError(f"mot-clé à la fois inclus et exclu : {', '.join(sorted(overlap))}")
        return self


class CompletenessOut(BaseModel):
    pct: int
    missing: list[str]
    missing_keys: list[str] = []  # identity, trades, watch, departments, revenue…


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trades: list[str]
    cpv_codes: list[str]
    keywords_include: list[str]
    keywords_exclude: list[str]
    departments: list[str]
    max_distance_km: int | None
    min_amount_cents: int | None
    max_amount_cents: int | None
    revenue_y1_cents: int | None
    revenue_y2_cents: int | None
    revenue_y3_cents: int | None
    min_score_alert: int
    completeness: CompletenessOut


class TradeOut(BaseModel):
    code: str
    label: str
    cpv_codes: list[str]
    keywords: list[str]


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class HumanResourceIn(BaseModel):
    qualification: Text
    count: int = Field(ge=0, le=100000)
    description: LongText | None = None


class HumanResourceOut(HumanResourceIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class EquipmentIn(BaseModel):
    name: Text
    category: Text | None = None
    quantity: int | None = Field(default=None, ge=0, le=1000000)
    spec_file_id: uuid.UUID | None = None


class EquipmentOut(EquipmentIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class CertificationIn(BaseModel):
    name: Text
    number: Text | None = None
    valid_until: date | None = None
    file_id: uuid.UUID | None = None


class CertificationOut(CertificationIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class ReferenceIn(BaseModel):
    client_name: Text
    client_type: str
    title: Text
    location: Text | None = None
    department: Department | None = None
    amount_cents: Cents | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    duration_months: int | None = Field(default=None, ge=0, le=1200)
    description: LongText | None = None
    cpv_codes: list[Cpv] = Field(default_factory=list, max_length=50)
    photo_file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @field_validator("client_type")
    @classmethod
    def _client_type(cls, v: str) -> str:
        if v not in ("public", "private"):
            raise ValueError("type de client : 'public' ou 'private'")
        return v

    @field_validator("cpv_codes", "photo_file_ids")
    @classmethod
    def _unique_list(cls, v: list) -> list:  # type: ignore[type-arg]
        return list(dict.fromkeys(v))


class ReferenceOut(ReferenceIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class ImportErrorOut(BaseModel):
    row: int
    message: str


class ImportReportOut(BaseModel):
    dry_run: bool
    total: int
    created: int
    errors: list[ImportErrorOut]
    ignored_columns: list[str] = Field(default_factory=list)
    skipped: list[ImportErrorOut] = Field(default_factory=list)  # duplicates, with the reason


Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class CompanyIn(BaseModel):
    """Identity and layout of the company (DC1/DC2, exports). The SIRET never changes."""

    name: Text
    legal_form: Short | None = None
    address_line: Short | None = None
    postal_code: Annotated[str, StringConstraints(pattern=r"^\d{5}$")] | None = None
    city: Short | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^\+?[\d .()-]{6,25}$")] | None = None
    contact_email: EmailStr | None = None
    signatory_name: Short | None = None
    signatory_role: Short | None = None
    logo_file_id: uuid.UUID | None = None
    brand_color: Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")] | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    siret: str
    siren: str
    naf_code: str | None
    headcount_range: str | None
    vat_number: str  # computed from the SIREN
    name: str
    legal_form: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    phone: str | None
    contact_email: str | None
    signatory_name: str | None
    signatory_role: str | None
    logo_file_id: uuid.UUID | None
    brand_color: str | None
