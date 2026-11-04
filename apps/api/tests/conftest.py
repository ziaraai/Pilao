import os
from collections.abc import Callable, Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://pilao:pilao@localhost:5432/pilao_test")

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.email import Email


def alembic_config(engine: Engine) -> Config:
    cfg = Config("alembic.ini")
    cfg.attributes["engine"] = engine
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ["DATABASE_URL"]
    # The fixture drops the whole schema: never let it run against a real database.
    assert url.rsplit("/", 1)[-1].endswith("_test"), "tests need a *_test database"
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(eng), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """One connection inside an outer transaction that is always rolled back."""
    connection = engine.connect()
    trans = connection.begin()
    yield connection
    trans.rollback()
    connection.close()


def _new_session(conn: Connection) -> Session:
    return Session(conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def db(conn: Connection) -> Iterator[Session]:
    session = _new_session(conn)
    yield session
    session.close()


class Outbox:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, message: Email) -> None:
        self.sent.append(message)

    def last_token(self) -> str:
        return self.sent[-1].body.split("token=")[1].split()[0]


class MemoryStorage:
    """In-memory ObjectStorage for API tests (S3 itself is covered with moto)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_put = False

    def put(self, key: str, fileobj, content_type: str) -> None:  # type: ignore[no-untyped-def]
        if self.fail_put:
            raise RuntimeError("storage down")
        self.objects[key] = fileobj.read()

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        return f"https://storage.test/{key}?name={filename}&expires={ttl_seconds}&sig=abc"


class FakeScanner:
    """Flags any content containing the EICAR marker; can simulate an outage."""

    def __init__(self) -> None:
        self.down = False

    def scan(self, fileobj) -> str | None:  # type: ignore[no-untyped-def]
        from app.storage.antivirus import ScannerUnavailable

        if self.down:
            raise ScannerUnavailable("down")
        fileobj.seek(0)
        found = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in fileobj.read()
        fileobj.seek(0)
        return "Eicar-Test-Signature" if found else None


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def scanner() -> FakeScanner:
    return FakeScanner()


class NoDirectory:
    """Default registry stub: knows no company."""

    def lookup_siret(self, siret: str) -> None:
        return None


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def make_client(
    conn: Connection,
    outbox: Outbox,
    storage: MemoryStorage,
    scanner: FakeScanner,
) -> Iterator[Callable[[], TestClient]]:
    """Factory of independent HTTP clients (own cookie jar), one DB session per request."""
    from app.core.email import get_mailer
    from app.db.session import get_db
    from app.integrations.recherche_entreprises import get_company_directory
    from app.main import app
    from app.routers.files import _scanner
    from app.storage.objects import get_storage

    def override_db() -> Iterator[Session]:
        with _new_session(conn) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_mailer] = lambda: outbox
    app.dependency_overrides[get_company_directory] = lambda: NoDirectory()  # never hit the network
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[_scanner] = lambda: scanner
    yield lambda: TestClient(app, headers={"Origin": "http://localhost:3000"})
    app.dependency_overrides.clear()
