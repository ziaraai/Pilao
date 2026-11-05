import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class GeneratedDocumentOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: Literal["pending", "ready", "error"]
    error: str | None
    file_id: uuid.UUID | None
    filename: str | None
    size_bytes: int | None
    to_complete: list[str]
    warnings: list[str]
    memoir_id: uuid.UUID | None
    created_at: datetime


class DocumentKindOut(BaseModel):
    kind: str
    label: str
    description: str
    latest: GeneratedDocumentOut | None


class ExportIn(BaseModel):
    format: Literal["docx", "pdf", "zip"]
    acknowledge_warnings: bool = False  # US-4.6 CA4: the user has read the warnings


class ChapterToComplete(BaseModel):
    section_id: uuid.UUID
    title: str
    items: list[str]


class MissingRequirement(BaseModel):
    ref: str
    text: str


class ExportCheckOut(BaseModel):
    warnings: list[str]
    to_complete: list[ChapterToComplete]
    missing_requirements: list[MissingRequirement]
    not_drafted: list[str]
    conformity_status: str
    estimated_pages: int | None
    max_pages: int | None
