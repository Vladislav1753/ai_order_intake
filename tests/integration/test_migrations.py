from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from tests.integration.conftest import run_alembic


def _schema_diff(connection: Connection) -> list[object]:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return list(compare_metadata(context, Base.metadata))


def _table_names(connection: Connection) -> list[str]:
    return inspect(connection).get_table_names()


async def test_migrations_match_models(migrated_engine: AsyncEngine) -> None:
    async with migrated_engine.connect() as connection:
        diff = await connection.run_sync(_schema_diff)
    assert diff == []


async def test_downgrade_removes_every_table(migrated_engine: AsyncEngine) -> None:
    await run_alembic(migrated_engine, "downgrade", "base")
    async with migrated_engine.connect() as connection:
        tables = await connection.run_sync(_table_names)
    assert tables == ["alembic_version"]
