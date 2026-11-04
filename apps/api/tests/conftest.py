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


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def make_client(conn: Connection, outbox: Outbox) -> Iterator[Callable[[], TestClient]]:
    """Factory of independent HTTP clients (own cookie jar), one DB session per request."""
    from app.core.email import get_mailer
    from app.db.session import get_db
    from app.main import app

    def override_db() -> Iterator[Session]:
        with _new_session(conn) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_mailer] = lambda: outbox
    yield lambda: TestClient(app, headers={"Origin": "http://localhost:3000"})
    app.dependency_overrides.clear()
