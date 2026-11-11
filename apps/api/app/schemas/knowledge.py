import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DocumentKind = Literal["memoir_template", "past_memoir", "qse_policy", "technical_sheet", "other"]


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    file_id: uuid.UUID
    kind: str
    title: str
    status: Literal["pending", "processing", "ready", "error"]
    error: str | None
    page_count: int | None
    chunk_count: int
    created_at: datetime


class SearchHitOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    heading: str | None
    page_from: int | None
    page_to: int | None
    content: str
    score: float


class KnowledgeKindIn(BaseModel):
    """« Modifier le type » of a document of the knowledge base: nothing is read again."""

    kind: DocumentKind
