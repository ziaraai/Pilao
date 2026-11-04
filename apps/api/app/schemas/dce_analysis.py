"""Pydantic mirror of schemas/dce_analysis.schema.json (output of prompts/extraction_dce.md).

Parsing is lenient on *form* (an unknown category becomes "other", "40 %" becomes 40), so one
odd field does not throw away a whole analysis. Sources are checked strictly afterwards, by
``app.services.dce_analysis.validate_sources``: an item whose source cannot be verified is
dropped (CLAUDE.md §5.2).
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

Category = Literal[
    "frequency",
    "surface",
    "product",
    "schedule",
    "staff",
    "equipment",
    "quality",
    "safety",
    "environment",
    "reporting",
    "other",
]
Importance = Literal["mandatory", "expected", "nice_to_have"]
Severity = Literal["info", "warning", "blocking"]


def _number(v: object) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    text = re.sub(r"[\s\u00a0€%]|HT", "", str(v)).replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _choice(v: object, allowed: tuple[str, ...], default: str) -> str:
    return v if isinstance(v, str) and v in allowed else default


def _keep_valid(v: object, item_model: type[BaseModel]) -> list[Any]:
    """Each item is validated on its own: a malformed one is dropped, the others are kept."""
    if not isinstance(v, list):
        return []
    kept = []
    for item in v:
        try:
            kept.append(item_model.model_validate(item))
        except ValidationError:
            continue
    return kept


class Source(BaseModel):
    file: str
    page: int | None = None

    @field_validator("page", mode="before")
    @classmethod
    def _page(cls, v: object) -> int | None:
        number = _number(v)
        return int(number) if number is not None and number >= 1 else None


class SourcedText(BaseModel):
    value: str | None = None
    source: Source | None = None


class SourcedNumber(BaseModel):
    value: float | None = None
    source: Source | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, v: object) -> float | None:
        return _number(v)


class Lot(BaseModel):
    number: str | None = None
    title: str
    estimated_amount_eur_ht: float | None = None
    source: Source | None = None

    @field_validator("number", mode="before")
    @classmethod
    def _num(cls, v: object) -> str | None:
        return None if v is None else str(v)

    @field_validator("estimated_amount_eur_ht", mode="before")
    @classmethod
    def _amount(cls, v: object) -> float | None:
        return _number(v)


class KeyInfo(BaseModel):
    buyer_name: SourcedText | None = None
    title: SourcedText | None = None
    procedure: SourcedText | None = None
    estimated_amount_eur_ht: SourcedNumber | None = None
    duration: SourcedText | None = None
    submission_deadline: SourcedText | None = None  # ISO 8601 text, parsed when used
    submission_platform: SourcedText | None = None
    lots: list[Lot] = Field(default_factory=list)

    @field_validator("lots", mode="before")
    @classmethod
    def _lots(cls, v: object) -> Any:
        return _keep_valid(v, Lot)


class SiteVisit(BaseModel):
    mandatory: bool | None = None
    dates: list[str] = Field(default_factory=list)
    details: str | None = None
    source: Source | None = None


class SubCriterion(BaseModel):
    name: str
    weight_pct: float | None = None

    @field_validator("weight_pct", mode="before")
    @classmethod
    def _w(cls, v: object) -> float | None:
        return _number(v)


class Criterion(BaseModel):
    name: str
    weight_pct: float | None = None
    subcriteria: list[SubCriterion] = Field(default_factory=list)
    source: Source | None = None

    @field_validator("weight_pct", mode="before")
    @classmethod
    def _w(cls, v: object) -> float | None:
        return _number(v)


class MemoirRequirements(BaseModel):
    imposed_outline: list[str] = Field(default_factory=list)
    response_template_provided: bool | None = None
    max_pages: int | None = None
    format_constraints: str | None = None
    source: Source | None = None

    @field_validator("max_pages", mode="before")
    @classmethod
    def _pages(cls, v: object) -> int | None:
        number = _number(v)
        return int(number) if number is not None and number > 0 else None


class RequiredDocument(BaseModel):
    name: str
    phase: Literal["candidature", "offre"] = "candidature"
    compliance_kind: str | None = None
    source: Source | None = None

    @field_validator("phase", mode="before")
    @classmethod
    def _phase(cls, v: object) -> str:
        return _choice(v, ("candidature", "offre"), "candidature")


class Requirement(BaseModel):
    ref: str = ""
    text: str
    category: Category = "other"
    importance: Importance = "expected"
    source: Source | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _cat(cls, v: object) -> str:
        return _choice(v, Category.__args__, "other")  # type: ignore[attr-defined]

    @field_validator("importance", mode="before")
    @classmethod
    def _imp(cls, v: object) -> str:
        return _choice(v, Importance.__args__, "expected")  # type: ignore[attr-defined]

    @field_validator("ref", mode="before")
    @classmethod
    def _ref(cls, v: object) -> str:
        return "" if v is None else str(v)


class WatchPoint(BaseModel):
    text: str
    severity: Severity = "info"
    source: Source | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def _sev(cls, v: object) -> str:
        return _choice(v, Severity.__args__, "info")  # type: ignore[attr-defined]


class DceAnalysisData(BaseModel):
    key_info: KeyInfo = Field(default_factory=KeyInfo)
    site_visit: SiteVisit = Field(default_factory=SiteVisit)
    questions_deadline: SourcedText | None = None
    award_criteria: list[Criterion] = Field(default_factory=list)
    memoir_requirements: MemoirRequirements = Field(default_factory=MemoirRequirements)
    required_documents: list[RequiredDocument] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    watch_points: list[WatchPoint] = Field(default_factory=list)

    @field_validator(
        "award_criteria", "required_documents", "requirements", "watch_points", mode="before"
    )
    @classmethod
    def _lists(cls, v: object, info: ValidationInfo) -> Any:
        return _keep_valid(v, _ITEM_MODELS[str(info.field_name)])


_ITEM_MODELS: dict[str, type[BaseModel]] = {
    "award_criteria": Criterion,
    "required_documents": RequiredDocument,
    "requirements": Requirement,
    "watch_points": WatchPoint,
}
