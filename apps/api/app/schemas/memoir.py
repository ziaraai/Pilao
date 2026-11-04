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


class RegenerateIn(BaseModel):
    instruction: str | None = Field(default=None, max_length=2000)
    # "compléter ce point" (US-4.3 CA2): requirements to hand to this chapter as well
    add_requirement_refs: list[str] = Field(default_factory=list, max_length=50)


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
    conformity_status: Literal["none", "pending", "ready", "error"]
    conformity_error: str | None
    drafted_words: int
    estimated_pages: int | None  # None until a chapter is drafted (US-4.2 CA5)
    page_warning: str | None
    created_at: datetime


class SourceRef(BaseModel):
    file: str
    page: int | None
    dce_file_id: uuid.UUID


class ConformityItemOut(BaseModel):
    requirement_ref: str
    requirement_text: str
    importance: str
    source: SourceRef | None
    status: Literal["covered", "partial", "missing"]
    method: Literal["ai", "declared"]
    excerpt: str | None
    comment: str | None
    section_id: uuid.UUID | None
    section_title: str | None
    # the chapter "compléter ce point" regenerates: the one quoted, else the one in the outline
    target_section_id: uuid.UUID | None


class ConformityOut(BaseModel):
    status: Literal["none", "pending", "ready", "error"]
    error: str | None
    counts: dict[str, int]
    items: list[ConformityItemOut]  # missing first, then partial, then covered (US-4.3 CA2)
