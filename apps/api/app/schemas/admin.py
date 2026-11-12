"""Schemas of the platform administration (``/admin``).

Supervision answers carry identities and counters only: no schema here has a field for the
text of a memoir, a DCE or a document, the title of a bid or a line of a company profile.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import siret_ok
from app.schemas.credits import HistoryOut


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
    kind: Literal["import", "job", "ai", "inactive", "credits"]
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
    siret: str
    city: str | None
    created_at: datetime
    users: int
    last_activity_at: datetime | None
    bids: int
    memoirs: int
    completeness_pct: int
    ai_cost_month: Decimal
    deletion_requested: bool
    suspended: bool
    suspended_at: datetime | None
    suspension_reason: str | None
    deletion_due_at: datetime | None
    invitation_pending: bool  # nobody of the company has created their access yet
    modules: list[str]  # its active modules, in the registry's order (lot 3)
    plan: "PlanRefOut"  # lot 4
    credits_total: int


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
    id: uuid.UUID
    full_name: str | None
    email: str
    role: str
    email_verified: bool
    last_login_at: datetime | None
    terms_version: str | None
    status: Literal["active", "unverified", "invited", "invitation_expired"]
    invited_at: datetime | None
    has_sessions: bool


class AccountStateOut(BaseModel):
    suspended_at: datetime | None
    suspension_reason: str | None
    deletion_due_at: datetime | None
    deletion_by: Literal["pilao", "client"] | None


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
    account: AccountStateOut
    counters: OrgCountersOut
    users: list[OrgUserOut]
    ai_months: list[AiMonthOut]  # the last six, oldest first
    ai_tasks: list[AiTaskOut]  # this month
    job_errors: list[JobIssueOut]  # 30 days
    feedback: list[FeedbackItemOut]
    modules: list[str]
    plan: "PlanRefOut"  # lot 4
    credits_total: int
    modules_off_plan: "ModulesOffPlanOut"


class AiCostOrgOut(BaseModel):
    org_id: uuid.UUID | None  # None: a call made for the platform itself
    name: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost: Decimal


class AiCostTaskOut(BaseModel):
    task: str
    label: str
    calls: int
    failures: int
    avg_latency_ms: int
    cost: Decimal


class AiCostModelOut(BaseModel):
    model: str
    calls: int
    cost: Decimal


class AiCostsOut(BaseModel):
    month: str  # "2026-11", a calendar month of Paris
    months: list[str]  # the twelve that can be asked for, the most recent first
    total: Decimal
    by_org: list[AiCostOrgOut]
    by_task: list[AiCostTaskOut]
    by_model: list[AiCostModelOut]


class ImportPassOut(BaseModel):
    source: str
    status: str
    started_at: datetime
    duration_seconds: int | None  # None: still running, or it died
    fetched: int
    created: int
    updated: int
    corrected: int
    skipped: int
    matched: int
    error: str | None


class SystemOut(BaseModel):
    imports: list[ImportPassOut]  # the latest 20 passes
    jobs: list[JobIssueOut]  # in error over 30 days, or stuck now; 50 at most


class FeedbackOut(BaseModel):
    days: int
    items: list[FeedbackItemOut]
    time_saved: list[TimeSavedRowOut]


# --- Lot 2: accounts -------------------------------------------------------------------


class AdminCreateOrgIn(BaseModel):
    siret: str
    name: str = Field(min_length=1, max_length=300)
    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: EmailStr
    plan_id: uuid.UUID | None = None  # lot 4: the default plan when none is chosen

    @field_validator("siret")
    @classmethod
    def _siret(cls, v: str) -> str:
        v = "".join(v.split())
        if not siret_ok(v):
            raise ValueError("SIRET invalide")
        return v


class CreatedOut(BaseModel):
    id: uuid.UUID
    email_sent: bool = True  # False: created, but the invitation e-mail did not leave


class SuspendIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Indiquez la raison de la suspension.")
        return v.strip()


class DeletionPreviewOut(BaseModel):
    """What « Supprimer » would do now, or the deletion already scheduled."""

    mode: Literal["immediate", "scheduled"]
    due_at: datetime | None
    pending: bool
    by: Literal["pilao", "client"] | None


class OrgDeleteIn(BaseModel):
    confirmation: str = Field(min_length=1, max_length=300)
    code: str = Field(min_length=1, max_length=40)


class OrgDeletionOut(BaseModel):
    mode: Literal["immediate", "scheduled"]
    due_at: datetime | None


class StepUpIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)


class AuditRowOut(BaseModel):
    id: uuid.UUID
    at: datetime
    admin_email: str
    action: str
    org_id: uuid.UUID | None
    org_name: str | None  # empty once the company is deleted
    ip: str | None
    meta: dict[str, object]


class AuditPageOut(BaseModel):
    rows: list[AuditRowOut]
    next_cursor: str | None  # pass it as ``cursor`` for the older lines


class ModuleOut(BaseModel):
    """A module of the registry, for the catalogue (lot 3)."""

    key: str
    name: str
    description: str
    contents: list[str]
    nav: list[str]
    organizations: int  # how many companies have it


class ModuleToggleIn(BaseModel):
    enabled: bool


class ModulesOut(BaseModel):
    modules: list[str]


# ---------- lot 4: plans and credits --------------------------------------------------------


class PlanRefOut(BaseModel):
    id: uuid.UUID
    name: str


class ModulesOffPlanOut(BaseModel):
    added: list[str]  # active although the plan does not give them
    removed: list[str]  # given by the plan but turned off


def _clean(value: str, *, required: bool, limit: int, what: str) -> str:
    value = " ".join(value.split())
    if required and not value:
        raise ValueError(f"{what} : champ obligatoire.")
    if len(value) > limit:
        raise ValueError(f"{what} : {limit} caractères maximum.")
    return value


class PlanIn(BaseModel):
    name: str
    description: str = ""
    modules: list[str] = Field(default_factory=list)
    monthly_credits: int = Field(default=0, ge=0, le=100_000)
    welcome_credits: int = Field(default=0, ge=0, le=100_000)
    price_note: str = ""

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return _clean(v, required=True, limit=80, what="Nom")

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        return _clean(v, required=False, limit=200, what="Phrase")

    @field_validator("price_note")
    @classmethod
    def _price(cls, v: str) -> str:
        return _clean(v, required=False, limit=120, what="Prix")

    @field_validator("modules")
    @classmethod
    def _modules(cls, v: list[str]) -> list[str]:
        from app.modules import BY_KEY, MODULES

        unknown = [k for k in v if k not in BY_KEY]
        if unknown:
            raise ValueError(f"Module inconnu : {', '.join(unknown)}.")
        return [m.key for m in MODULES if m.key in v]


class PlanOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    modules: list[str]
    monthly_credits: int
    welcome_credits: int
    price_note: str
    is_default: bool
    archived: bool
    organizations: int


class PlanUpdateOut(BaseModel):
    plan: PlanOut
    organizations_affected: int


class CreditPriceIn(BaseModel):
    credits: int = Field(ge=0, le=1000)


class CreditPriceOut(BaseModel):
    action: str
    name: str
    module: str
    credits: int
    default_credits: int
    uses_30d: int  # paid and not given back, the last 30 days
    avg_cost_30d: Decimal | None  # real AI cost per use, in euros: the administration only


class OrgPlanIn(BaseModel):
    plan_id: uuid.UUID


class CreditsGrantIn(BaseModel):
    amount: int = Field(ge=1, le=100_000)
    reason: str

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str) -> str:
        return _clean(v, required=True, limit=200, what="Raison")


class OrgCreditsOut(BaseModel):
    plan: PlanRefOut
    monthly_allowance: int
    monthly_left: int
    extra: int
    total: int
    renews_on: date
    history: list[HistoryOut]


# ---------- lot 5: platform settings ----------------------------------------------------------

Origin = Literal["admin", "server"]


class ModelSettingOut(BaseModel):
    task: str
    label: str
    model: str  # the LiteLLM name in use ("" = none)
    model_name: str | None  # its catalogue name, when the catalogue is known
    source: Origin
    server_model: str
    price_in_eur: float | None  # per million tokens, None when the catalogue is not known
    price_out_eur: float | None
    in_catalogue: bool | None
    cost_30d_eur: float
    calls_30d: int
    updated_at: datetime | None


class CreditOut(BaseModel):
    total_usd: float
    used_usd: float


class ApiKeyOut(BaseModel):
    source: Literal["admin", "server", "none"]
    last4: str | None  # never the key itself
    updated_at: datetime | None
    unreadable: bool
    server_key: bool
    credit: CreditOut | None


class LastPassOut(BaseModel):
    started_at: datetime
    status: str
    created: int
    updated: int
    error: str | None


class ImportSettingOut(BaseModel):
    source: str
    label: str
    enabled: bool
    origin: Origin
    last: LastPassOut | None


class GeneralSettingOut(BaseModel):
    name: str
    label: str
    kind: Literal["int", "email"]
    value: int | float | str | None
    server_value: int | float | str | None
    source: Origin


class SettingsOut(BaseModel):
    models: list[ModelSettingOut]
    embedding_model: str
    api_key: ApiKeyOut
    imports: list[ImportSettingOut]
    general: list[GeneralSettingOut]


class CatalogueModelOut(BaseModel):
    id: str
    name: str
    price_in_eur: float
    price_out_eur: float
    context_length: int


class ModelChoiceIn(BaseModel):
    model_id: str = Field(min_length=1, max_length=200)


class ApiKeyIn(BaseModel):
    key: str = Field(max_length=200)

    @field_validator("key")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Collez la clé OpenRouter.")
        return v
