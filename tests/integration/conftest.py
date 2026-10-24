from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.migrations import run_alembic
from app.db.session import make_engine, make_sessionmaker


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
