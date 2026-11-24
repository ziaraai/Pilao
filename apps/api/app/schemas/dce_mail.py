import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class DceMailOut(BaseModel):
    address: str
    active: bool  # the mailbox is switched on: the address can be used


class SuggestedBidOut(BaseModel):
    id: uuid.UUID
    title: str


class SkippedOut(BaseModel):
    path: str
    reason: str


class InboundMailOut(BaseModel):
    id: uuid.UUID
    received_at: datetime
    sender: str
    subject: str
    kind: Literal["dce", "notice"]
    attachments: list[str]
    skipped: list[SkippedOut]
    links: list[str]
    suggested_bid: SuggestedBidOut | None
    note: str | None


class FileMailIn(BaseModel):
    bid_id: uuid.UUID
    mode: Literal["new", "add"] = "new"


class FiledOut(BaseModel):
    bid_id: uuid.UUID
    version: int | None  # None: a link put in the dossier (no piece)


class NewBidOut(BaseModel):
    bid_id: uuid.UUID


class DceNoticeOut(BaseModel):
    id: uuid.UUID
    received_at: datetime
    sender: str
    subject: str
    links: list[str]
