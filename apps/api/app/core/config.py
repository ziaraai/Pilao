from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_prompts_dir() -> str:
    """The nearest ``prompts`` folder above this file: the repository root in development,
    ``/app/prompts`` in the image (where PROMPTS_DIR is also set)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "prompts").is_dir():
            return str(parent / "prompts")
    return str(here.parents[2] / "prompts")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pilao:pilao@localhost:5432/pilao"
    redis_url: str = "redis://localhost:6379/0"
    app_secret_key: str = "change-me"
    app_base_url: str = "http://localhost:3000"
    recherche_entreprises_base_url: str = "https://recherche-entreprises.api.gouv.fr"
    s3_endpoint: str | None = None  # None = AWS / provider default; MinIO locally
    s3_bucket: str = "pilao-local"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "fr-par"
    max_upload_bytes: int = 50 * 1024 * 1024
    # DCE archives often carry plans: a larger limit, for that endpoint only.
    max_dce_upload_bytes: int = 250 * 1024 * 1024
    org_storage_quota_bytes: int = 5 * 1024**3
    signed_url_ttl_seconds: int = 300
    clamav_host: str | None = None  # unset = no antivirus (refused in production)
    clamav_port: int = 3310
    # LibreOffice for the PDF export (worker image); empty = PDF export unavailable
    soffice_path: str = "soffice"
    pdf_timeout_seconds: int = 180
    # GDPR (ADR-026): an organization's deletion runs this long after the request (cancellable)
    deletion_grace_days: int = 30
    # LLM models per task (LiteLLM names), fixed after phase 0 (ADR-005). Empty = not configured.
    llm_model_extraction: str = ""
    llm_model_generation: str = ""
    llm_model_scoring: str = ""
    llm_model_vision: str = ""
    ai_monthly_budget_eur_per_org: float = 50.0
    # Added to each call's answer limit: recent models reason (billed, hidden) before answering
    llm_reasoning_tokens: int = 8000
    # Through OpenRouter: never a provider that stores or trains on requests (privacy policy);
    # zero data retention only, optionally (some models then become unavailable)
    llm_deny_data_collection: bool = True
    llm_zero_data_retention: bool = False
    # Providers bill in US dollars (LiteLLM prices are in USD): costs are stored in euros
    usd_eur_rate: float = 0.86
    # DCE text sent per analysis call (~3.8 chars/token: 300k chars ≈ 80k tokens).
    dce_analysis_max_chars: int = 300_000
    dce_analysis_max_calls: int = 8
    prompts_dir: str = Field(default_factory=lambda: _default_prompts_dir())
    # Embedding model (LiteLLM name, e.g. "openrouter/..."), fixed after phase 0 (ADR-005).
    # Empty = deterministic local HashEmbedder (development and tests only).
    embedding_model: str = ""
    embedding_dim: int = 1024  # changing it needs a migration AND a full re-embedding
    # Secure by default: without an explicit ENVIRONMENT=local|test, production rules apply
    # (real antivirus and embeddings required, Secure cookies).
    environment: str = "production"  # local | test | production

    session_cookie_name: str = "pilao_session"
    session_ttl_hours: int = 24 * 14
    email_verify_ttl_hours: int = 48
    invitation_ttl_hours: int = 24 * 7  # link sent to an invited colleague
    max_users_per_org: int = 25  # guard; the real limit will come with the plans (Q3)
    email_verify_max_per_hour: int = 5  # resend cap per account (anti mail-bombing)
    login_max_failures_per_email: int = 5
    login_max_failures_per_ip: int = 30
    login_window_minutes: int = 15
    login_attempts_retention_days: int = 30  # then purged (privacy policy)

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"

    def production_problems(self) -> list[str]:
        """Settings that must never reach production: the API refuses to start with them."""
        if self.environment != "production":
            return []
        problems = []
        if not self.app_base_url.startswith("https://"):
            problems.append("APP_BASE_URL doit être en https:// (cookies sécurisés).")
        if "pilao:pilao@" in self.database_url or "localhost" in self.database_url:
            problems.append("DATABASE_URL utilise les identifiants ou l'hôte de développement.")
        if self.s3_bucket == "pilao-local" or not (self.s3_access_key and self.s3_secret_key):
            problems.append("S3_BUCKET, S3_ACCESS_KEY et S3_SECRET_KEY de production sont requis.")
        if not self.clamav_host:
            problems.append("CLAMAV_HOST est requis (antivirus des fichiers déposés).")
        if not self.embedding_model:
            problems.append("EMBEDDING_MODEL est requis (recherche dans la base documentaire).")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
