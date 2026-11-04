"""What the models must return for a chapter and for the conformity matrix (lenient on form)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


def _strings(v: object) -> list[str]:
    return (
        [str(x) for x in v if isinstance(x, str | int | float) and str(x).strip()]
        if isinstance(v, list)
        else []
    )


class SourceUse(BaseModel):
    excerpt_id: str
    used_for: str = ""


class ChapterOut(BaseModel):
    markdown: str = Field(min_length=1)
    covered_requirements: list[str] = Field(default_factory=list)
    sources: list[SourceUse] = Field(default_factory=list)
    to_complete: list[str] = Field(default_factory=list)
    commitments: list[str] = Field(default_factory=list)

    @field_validator("covered_requirements", "to_complete", "commitments", mode="before")
    @classmethod
    def _lists(cls, v: object) -> list[str]:
        return _strings(v)

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
