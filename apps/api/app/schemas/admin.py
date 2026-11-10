"""Schemas of the platform administration (``/admin``).

Supervision answers carry identities and counters only: no schema here has a field for the
text of a memoir, a DCE or a document, the title of a bid or a line of a company profile.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class SetupLookupIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class SetupLookupOut(BaseModel):
    email: str


class SetupPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=200)


class SetupPasswordOut(BaseModel):
    """Shown once, during the activation: the secret never leaves the server afterwards."""

    secret: str
    otpauth_uri: str
    qr_svg: str


class SetupConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)


class AdminMeOut(BaseModel):
    email: str
    full_name: str | None
    recovery_codes_left: int
    previous_login_at: datetime | None  # to spot a sign-in that was not yours


class SetupConfirmOut(BaseModel):
    recovery_codes: list[str]  # shown once
    me: AdminMeOut


class AdminLoginIn(BaseModel):
    # Plain strings on purpose: a malformed address gets the same refusal as a wrong one.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)


# --- Supervision (read-only) -------------------------------------------------------------


class CountersOut(BaseModel):
    organizations: int
    active_7d: int
    bids_open: int
    memoirs_done: int
    ai_cost_month: Decimal
    job_errors_24h: int


class WatchItemOut(BaseModel):
    level: Literal["red", "amber"]
    kind: Literal["import", "job", "ai", "inactive"]
    title: str
    detail: str | None
    at: datetime | None
    org_id: uuid.UUID | None


class ActivityRowOut(BaseModel):
    org_id: uuid.UUID
    name: str
    logins: int
    bids: int
    memoirs: int
    exports: int


class ImportRowOut(BaseModel):
    """The latest pass of a notice reader."""

    source: str
    enabled: bool
    status: str | None  # None: never ran
    started_at: datetime | None
    fetched: int | None
    created: int | None
    error: str | None


class TimeSavedRowOut(BaseModel):
    name: str
    bids: int
    minutes_saved: int
    percent: int | None


class OverviewOut(BaseModel):
    counters: CountersOut
    watch: list[WatchItemOut]
    more_job_issues: int
    activity: list[ActivityRowOut]
    imports: list[ImportRowOut]
    time_saved: list[TimeSavedRowOut]


class OrganizationRowOut(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    created_at: datetime
    users: int
    last_activity_at: datetime | None
    bids: int
    memoirs: int
    completeness_pct: int
    ai_cost_month: Decimal
    deletion_requested: bool


class OrgIdentityOut(BaseModel):
    name: str
    siret: str
    legal_form: str | None
    naf_code: str | None
    postal_code: str | None
    city: str | None
    created_at: datetime
    trades: list[str]
    departments: list[str]
    last_activity_at: datetime | None
    deletion_requested: bool


class OrgCountersOut(BaseModel):
    bids: int
    bids_by_status: dict[str, int]
    memoirs_done: int
    knowledge_documents: int
    compliance_valid: int
    compliance_expired: int
    completeness_pct: int
    ai_cost_month: Decimal


class OrgUserOut(BaseModel):
    full_name: str | None
    email: str
    role: str
    email_verified: bool
    last_login_at: datetime | None
    terms_version: str | None


class AiMonthOut(BaseModel):
    month: str  # "2026-11"
    cost: Decimal


class AiTaskOut(BaseModel):
    task: str
    label: str
    calls: int
    cost: Decimal


class JobIssueOut(BaseModel):
    kind: str
    label: str
    org_id: uuid.UUID | None
    org_name: str | None
    state: Literal["error", "stuck"]
    at: datetime
    message: str | None  # the one the user already sees: may name a file, never quotes one


class FeedbackItemOut(BaseModel):
    created_at: datetime
    org_name: str
    user_email: str | None
    kind: str
    page: str | None
    message: str


class OrganizationDetailOut(BaseModel):
    identity: OrgIdentityOut
    counters: OrgCountersOut
    users: list[OrgUserOut]
    ai_months: list[AiMonthOut]  # the last six, oldest first
    ai_tasks: list[AiTaskOut]  # this month
    job_errors: list[JobIssueOut]  # 30 days
    feedback: list[FeedbackItemOut]
