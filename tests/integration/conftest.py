from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import PROJECT_ROOT
from app.db.session import make_engine, make_sessionmaker


def _alembic(connection: Connection, action: str, revision: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.attributes["connection"] = connection
    getattr(command, action)(config, revision)


async def run_alembic(engine: AsyncEngine, action: str, revision: str) -> None:
    """Run `alembic upgrade|downgrade <revision>` against `engine` instead of the app DB."""
    async with engine.begin() as connection:
        await connection.run_sync(_alembic, action, revision)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    yield engine
    await engine.dispose()


@pytest.fixture
async def migrated_engine(engine: AsyncEngine) -> AsyncEngine:
    await run_alembic(engine, "upgrade", "head")
    return engine


@pytest.fixture
async def session(migrated_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with make_sessionmaker(migrated_engine)() as session:
        yield session
