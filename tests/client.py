from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx2 import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@asynccontextmanager
async def app_client(settings: Settings | None = None) -> AsyncIterator[AsyncClient]:
    """A client for a freshly started app. Leaving the block shuts the app down."""
    app = create_app(settings)
    # ASGITransport doesn't send lifespan events, so run the lifespan explicitly.
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client
