"""What the models must return for a chapter and for the conformity matrix (lenient on form)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.domain.missing import KINDS, MissingKind


def _strings(v: object) -> list[str]:
    return (
        [str(x) for x in v if isinstance(x, str | int | float) and str(x).strip()]
        if isinstance(v, list)
        else []
    )


class SourceUse(BaseModel):
    excerpt_id: str
    used_for: str = ""


class ToComplete(BaseModel):
    """A missing item and its drawer of the profile (``None``: the model did not say)."""

    text: str
    kind: MissingKind | None = None


def _to_complete(v: object) -> list[ToComplete]:
    if not isinstance(v, list):
        return []
    kept = []
    for item in v:
        if isinstance(item, str | int | float) and str(item).strip():
            kept.append(ToComplete(text=str(item).strip()))
        elif isinstance(item, dict) and str(item.get("text") or "").strip():
            kind = item.get("kind")
            kept.append(
                ToComplete(text=str(item["text"]).strip(), kind=kind if kind in KINDS else None)
            )
    return kept


class MarkerFillOut(BaseModel):
    """One sentence completed with the company's data (« Ce qu'il manque », ADR-048)."""

    sentence: str = Field(min_length=1)
    filled: bool = False


class ChapterOut(BaseModel):
    markdown: str = Field(min_length=1)
    covered_requirements: list[str] = Field(default_factory=list)
    sources: list[SourceUse] = Field(default_factory=list)
    to_complete: list[ToComplete] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)

    @field_validator("covered_requirements", "commitments", mode="before")
    @classmethod
    def _lists(cls, v: object) -> list[str]:
        return _strings(v)

    @field_validator("to_complete", mode="before")
    @classmethod
    def _todos(cls, v: object) -> list[ToComplete]:
        return _to_complete(v)

    @field_validator("sources", mode="before")
    @classmethod
    def _sources(cls, v: object) -> list[Any]:
        if not isinstance(v, list):
            return []
        kept = []
        for item in v:
            try:
                kept.append(SourceUse.model_validate(item))
            except ValidationError:
                continue
        return kept


class MatrixItem(BaseModel):
    requirement_ref: str
    status: Literal["covered", "partial", "missing"] = "missing"
    section_id: str | None = None
    excerpt: str | None = None
    comment: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _status(cls, v: object) -> str:
        return v if v in ("covered", "partial", "missing") else "missing"


class MatrixOut(BaseModel):
    items: list[MatrixItem] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: object) -> list[Any]:
        if not isinstance(v, list):
            return []
        kept = []
        for item in v:
            try:
                kept.append(MatrixItem.model_validate(item))
            except ValidationError:
                continue
        return kept
