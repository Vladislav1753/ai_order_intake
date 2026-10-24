"""Command line entry point: `uv run python -m app.cli <command>` (wrapped by justfile recipes)."""

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from app.core.config import Settings, get_settings
from app.db.session import make_engine, make_sessionmaker
from app.schemas.seed import CatalogItem, SeedFile
from app.services.catalog import load_catalog


def read_seed_file(path: Path) -> SeedFile:
    return SeedFile.model_validate_json(path.read_text(encoding="utf-8"))


async def seed(settings: Settings, items: Sequence[CatalogItem]) -> int:
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            return await load_catalog(session, items)
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="order-intake")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="load the catalog from data/seed/seed.json into the database")
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.command == "seed":
        seed_file = read_seed_file(settings.seed_dir / "seed.json")
        count = asyncio.run(seed(settings, seed_file.catalog))
        print(f"Loaded {count} products into {settings.database_url}")


if __name__ == "__main__":
    main()
