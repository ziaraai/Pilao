"""A company's credits as it sees them (lot 4): never a euro."""

from datetime import date, datetime

from pydantic import BaseModel


class MeCreditsOut(BaseModel):
    total: int
    reference: int  # what the low-credits banner compares with
    prices: dict[str, int]


class PlanBriefOut(BaseModel):
    name: str
    description: str
    modules: list[str]


class PriceOut(BaseModel):
    action: str
    name: str
    credits: int


class HistoryOut(BaseModel):
    at: datetime
    kind: str
    action_name: str | None
    bid_title: str | None
    user_name: str | None
    credits: int
    reason: str | None


class CreditsOut(BaseModel):
    plan: PlanBriefOut
    monthly_allowance: int
    monthly_left: int
    extra: int
    total: int
    renews_on: date
    prices: list[PriceOut]
    history: list[HistoryOut]
