import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class OutlineSectionIn(BaseModel):
    id: uuid.UUID | None = None  # None = new chapter
    title: Title
    requirement_refs: list[str] = Field(default_factory=list, max_length=500)
    word_budget: int = Field(default=400, ge=50, le=10_000)


class OutlineIn(BaseModel):
    sections: list[OutlineSectionIn] = Field(min_length=1, max_length=60)


class ReferencesIn(BaseModel):
    reference_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class SectionOut(BaseModel):
    id: uuid.UUID
    position: int
    title: str
    criterion_ref: str | None
    criterion_weight: float | None
    requirement_refs: list[str]
    word_budget: int
    status: str
    error: str | None
    content_md: str | None
    flags: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    covered_refs: list[str]
    edited_by_user: bool


class ReferenceChoiceOut(BaseModel):
    id: uuid.UUID
    client_name: str
    title: str
    year: int | None
    amount_cents: int | None
    score: float | None
    reasons: list[str]
    selected: bool


class MemoirOut(BaseModel):
    id: uuid.UUID
    version: int
    status: Literal["draft", "generating", "ready", "exported"]
    outline_source: Literal["rc_imposed", "org_template", "sector_default"]
    max_pages: int | None
    word_budget: int
    sections: list[SectionOut]
    references: list[ReferenceChoiceOut]
    unassigned_requirements: list[str]
    created_at: datetime
