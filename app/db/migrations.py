from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import PROJECT_ROOT


def _alembic(connection: Connection, action: str, revision: str) -> None:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.attributes["connection"] = connection
    getattr(command, action)(config, revision)


async def run_alembic(engine: AsyncEngine, action: str, revision: str) -> None:
    """Run `alembic upgrade|downgrade <revision>` against `engine` instead of the app DB."""
    async with engine.begin() as connection:
        await connection.run_sync(_alembic, action, revision)
