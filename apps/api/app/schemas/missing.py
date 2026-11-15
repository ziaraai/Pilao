"""« Ce qu'il manque » (ADR-048): what is missing in a dossier, and how to fill it."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.missing import MissingKind


class MissingSectionOut(BaseModel):
    id: uuid.UUID
    title: str


class MissingFillOut(BaseModel):
    status: Literal["pending", "running", "done", "error"]
    outcome: Literal["filled", "not_enough"] | None
    error: str | None


class MissingItemOut(BaseModel):
    key: str
    text: str
    kind: MissingKind
    sections: list[MissingSectionOut]  # the chapters holding it
    documents: list[str]  # the DC1/DC2… kinds holding it
    fill: MissingFillOut | None  # the latest completion asked for it


class ProfileGapsOut(BaseModel):
    """``True``: the profile has none of them (the memoir will have holes)."""

    staff: bool
    equipment: bool
    references: bool


class MissingOut(BaseModel):
    memoir_id: uuid.UUID | None
    memoir_busy: bool  # a chapter is being drafted: nothing can be changed meanwhile
    items: list[MissingItemOut]
    profile_gaps: ProfileGapsOut


class MissingKeyIn(BaseModel):
    key: str = Field(min_length=1, max_length=300)


class MissingAnswerIn(MissingKeyIn):
    answer: str = Field(max_length=2000)
