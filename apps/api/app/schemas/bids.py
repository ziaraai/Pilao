import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BidStatus = Literal["to_review", "in_progress", "submitted", "won", "lost", "dropped"]
DceKind = Literal["rc", "ccap", "cctp", "ae", "bpu", "dpgf", "dqe", "annex", "other"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class BidIn(BaseModel):
    title: Text
    buyer_name: Text | None = None
    reference: Text | None = None
    deadline_at: datetime | None = None
    lot_label: Text | None = None


class BidPatch(BaseModel):
    """Partial update: only the fields sent are changed."""

    title: Text | None = None
    buyer_name: Text | None = None
    reference: Text | None = None
    deadline_at: datetime | None = None
    lot_label: Text | None = None
    status: BidStatus | None = None
    submitted_amount_cents: Annotated[int, Field(ge=0, le=10**13)] | None = None
    result_rank: Annotated[int, Field(ge=1, le=1000)] | None = None
    result_notes: LongText | None = None


class BidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    buyer_name: str | None
    reference: str | None
    deadline_at: datetime | None
    status: BidStatus
    lot_label: str | None
    submitted_amount_cents: int | None
    result_rank: int | None
    result_notes: str | None
    created_at: datetime


class DceFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    file_id: uuid.UUID
    path: str
    detected_kind: DceKind
    kind_source: str
    kind_confirmed: bool
    page_count: int | None
    ocr_used: bool
    text_status: str
    text_error: str | None
    paginated: bool


class DcePageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    page: int
    text: str
    ocr_used: bool


class DceVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    version: int
    status: Literal["pending", "processing", "ready", "error"]
    error: str | None
    skipped: list[dict[str, Any]]
    diff: dict[str, Any] | None
    diff_summary: str | None
    created_at: datetime
    files: list[DceFileOut] = Field(default_factory=list)


class DceKindIn(BaseModel):
    kind: DceKind
