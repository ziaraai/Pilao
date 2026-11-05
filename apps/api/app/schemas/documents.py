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
