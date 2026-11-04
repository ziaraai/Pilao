import os
from collections.abc import Iterator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://pilao:pilao@localhost:5432/pilao_test")

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command


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
def db(engine: Engine) -> Iterator[Session]:
    """A session wrapped in an outer transaction that is always rolled back."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    trans.rollback()
    conn.close()
