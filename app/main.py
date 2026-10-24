from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.core.config import Settings, get_settings
from app.db.session import make_engine, make_sessionmaker
from app.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    # The engine lives for the app's lifetime and is created inside its event loop.
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        app.state.sessionmaker = make_sessionmaker(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="Order Intake", debug=settings.debug, lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(health.router)
    return app


app = create_app()
