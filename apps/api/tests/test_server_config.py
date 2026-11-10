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


DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def trusted_proxies() -> str:
    """The ``--forwarded-allow-ips`` the API image starts uvicorn with."""
    import json

    found = re.search(r"^CMD (\[.*\])$", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert found, "no CMD in the API Dockerfile"
    command: list[str] = json.loads(found.group(1))
    return command[command.index("--forwarded-allow-ips") + 1]


def test_a_client_cannot_choose_the_address_the_api_sees() -> None:
    """nginx appends the address it saw to whatever X-Forwarded-For the client sent: the API
    must take that last address, or the per-address lock and the audit log are the client's
    to choose."""
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    trusted = _TrustedHosts(trusted_proxies())
    assert trusted.get_trusted_client_address("6.6.6.6, 203.0.113.7")[0] == "203.0.113.7"
    assert trusted.get_trusted_client_address("10.0.0.5, 203.0.113.7")[0] == "203.0.113.7"
    assert trusted.get_trusted_client_address("203.0.113.7")[0] == "203.0.113.7"
    # whatever network Docker gives the compose project, its gateway (nginx's way in) is trusted,
    # or every visitor would share one address and one lock
    for gateway in (
        "127.0.0.1",
        "172.17.0.1",
        "172.18.0.1",
        "172.31.0.1",
        "192.168.16.1",
        "10.0.0.1",
    ):
        assert gateway in trusted, gateway
