import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    res = TestClient(app).get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_ready_reports_each_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    from redis.exceptions import ConnectionError as RedisDown

    from app import main

    class Ping:
        def __init__(self, ok: bool) -> None:
            self.ok = ok

        def ping(self) -> bool:
            if not self.ok:
                raise RedisDown("down")
            return True

    monkeypatch.setattr(main.Redis, "from_url", staticmethod(lambda *a, **k: Ping(True)))
    res = TestClient(app).get("/ready")
    assert res.status_code == 200 and res.json() == {
        "status": "ok",
        "database": "ok",
        "redis": "ok",
    }
    monkeypatch.setattr(main.Redis, "from_url", staticmethod(lambda *a, **k: Ping(False)))
    res = TestClient(app).get("/ready")
    assert res.status_code == 503 and res.json()["redis"] == "unavailable"


def test_production_refuses_development_settings() -> None:
    from app.core.config import Settings

    dev = Settings(  # the development defaults, whatever this shell exports
        _env_file=None,  # type: ignore[call-arg]
        environment="production",
        app_base_url="http://localhost:3000",
        database_url="postgresql+psycopg://pilao:pilao@localhost:5432/pilao",
        s3_bucket="pilao-local",
        s3_access_key="",
        s3_secret_key="",
        clamav_host=None,
        embedding_model="",
    )
    assert len(dev.production_problems()) == 5
    prod = Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="production",
        app_base_url="https://app.pilao.fr",
        database_url="postgresql+psycopg://pilao_app:secret@db.internal:5432/pilao",
        s3_bucket="pilao-prod",
        s3_access_key="AK",
        s3_secret_key="SK",
        clamav_host="clamav",
        embedding_model="openrouter/some-embedding-model",
    )
    assert prod.production_problems() == []
    assert Settings(environment="local", _env_file=None).production_problems() == []  # type: ignore[call-arg]
