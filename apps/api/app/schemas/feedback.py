"""Feedback from users (P4-02)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FeedbackKind = Literal["idea", "problem", "question"]


class FeedbackIn(BaseModel):
    kind: FeedbackKind
    message: str = Field(min_length=1, max_length=4000)
    page: str | None = Field(default=None, max_length=300)  # where it was written
    bid_id: uuid.UUID | None = None


class FeedbackOut(BaseModel):
    id: uuid.UUID
    kind: FeedbackKind
    created_at: datetime
