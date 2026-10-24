import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# Point the app at a throwaway database before any settings are read, and never call a live model.
_TEST_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"
os.environ["MODEL_MODE"] = "replay"

import pytest  # noqa: E402
from httpx2 import AsyncClient  # noqa: E402

from tests.client import app_client  # noqa: E402


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with app_client() as client:
        yield client
