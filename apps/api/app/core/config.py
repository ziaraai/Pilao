from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pilao:pilao@localhost:5432/pilao"
    redis_url: str = "redis://localhost:6379/0"
    app_secret_key: str = "change-me"
    app_base_url: str = "http://localhost:3000"
    recherche_entreprises_base_url: str = "https://recherche-entreprises.api.gouv.fr"
    environment: str = "local"  # local | test | production

    session_cookie_name: str = "pilao_session"
    session_ttl_hours: int = 24 * 14
    email_verify_ttl_hours: int = 48
    password_min_length: int = 12
    login_max_failures_per_email: int = 5
    login_max_failures_per_ip: int = 30
    login_window_minutes: int = 15

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
