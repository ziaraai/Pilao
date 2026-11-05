"""The server deployment files (infra/server, ADR-033) are checked before any deploy: a bad
app.env would make the API refuse to start in production, and a port that differs between
compose, nginx and deploy.sh would leave the site unreachable."""

import re
from pathlib import Path

import pytest

from app.core.config import Settings

SERVER = Path(__file__).resolve().parents[3] / "infra" / "server"
pytestmark = pytest.mark.skipif(not SERVER.exists(), reason="infra/ absent (API image)")


def env_file(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def test_the_server_settings_pass_the_production_checks() -> None:
    values = env_file(SERVER / "app.env")
    assert values["ENVIRONMENT"] == "production" and values["STORAGE_BACKEND"] == "disk"
    secrets = {  # what deploy.sh generates on the server, and the GitHub secrets
        "DATABASE_URL": "postgresql+psycopg://pilao:0123456789abcdef@postgres:5432/pilao",
        "APP_SECRET_KEY": "a" * 64,
        "OPENROUTER_API_KEY": "sk-or-v1-test",
        "SMTP_PASSWORD": "x",
    }
    settings = Settings(_env_file=None, **{k.lower(): v for k, v in {**values, **secrets}.items()})  # type: ignore[arg-type]
    assert settings.production_problems() == []
    assert settings.api_public_url == settings.app_base_url + "/api"  # same origin: one cookie
    assert not any(k in values for k in ("OPENROUTER_API_KEY", "SMTP_PASSWORD", "APP_SECRET_KEY"))


def test_ports_agree_between_compose_nginx_and_the_deploy_check() -> None:
    compose = (SERVER / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (SERVER / "nginx-plesk.conf").read_text(encoding="utf-8")
    deploy = (SERVER / "deploy.sh").read_text(encoding="utf-8")
    api = re.search(r'"127\.0\.0\.1:(\d+):8000"', compose)
    web = re.search(r'"127\.0\.0\.1:(\d+):3000"', compose)
    assert api and web  # published on the loopback only
    assert f"proxy_pass http://127.0.0.1:{api[1]}/;" in nginx  # /api/ prefix stripped
    assert f"proxy_pass http://127.0.0.1:{web[1]};" in nginx
    assert f"http://127.0.0.1:{api[1]}/ready" in deploy and f"http://127.0.0.1:{web[1]}/" in deploy
    assert re.findall(r'"(\d+\.\d+\.\d+\.\d+:)?\d+:\d+"', compose) == ["127.0.0.1:", "127.0.0.1:"]
