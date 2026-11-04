from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # LLM models per task (LiteLLM names), fixed after phase 0 (ADR-005). Empty = not configured.
    llm_model_extraction: str = ""
    llm_model_generation: str = ""
    llm_model_scoring: str = ""
    llm_model_vision: str = ""
    ai_monthly_budget_eur_per_org: float = 50.0
    # DCE text sent per analysis call (~3.8 chars/token: 300k chars ≈ 80k tokens).
    dce_analysis_max_chars: int = 300_000
    dce_analysis_max_calls: int = 8
    prompts_dir: str = str(Path(__file__).resolve().parents[4] / "prompts")
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
    email_verify_max_per_hour: int = 5  # resend cap per account (anti mail-bombing)
    login_max_failures_per_email: int = 5
    login_max_failures_per_ip: int = 30
    login_window_minutes: int = 15

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
