import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# Point the app at a throwaway database before any settings are read, and never call a live model.
_TEST_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"
os.environ["MODEL_MODE"] = "replay"

import pytest  # noqa: E402
from httpx2 import ASGITransport, AsyncClient  # noqa: E402

from app.main import create_app  # noqa: E402


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    # ASGITransport doesn't send lifespan events, so run the lifespan explicitly.
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client
