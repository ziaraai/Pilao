from sqlalchemy import Engine, inspect

from alembic import command
from app.db.base import Base
from tests.conftest import alembic_config


def test_migrations_match_models_and_roundtrip(engine: Engine) -> None:
    cfg = alembic_config(engine)
    command.downgrade(cfg, "base")
    assert "organizations" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())


def test_every_org_scoped_table_has_org_id_index(engine: Engine) -> None:
    insp = inspect(engine)
    for name, table in Base.metadata.tables.items():
        if "org_id" in table.c:
            indexed = [i["column_names"][0] for i in insp.get_indexes(name)]
            assert "org_id" in indexed, f"{name} lacks an org_id index"
