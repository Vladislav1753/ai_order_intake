"""Command line entry point: `uv run python -m app.cli <command>` (wrapped by justfile recipes)."""

import argparse
import asyncio
import logging
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.enums import RequestStatus
from app.db.session import make_engine, make_sessionmaker
from app.providers.factory import make_provider
from app.schemas.seed import CatalogItem, SeedFile
from app.services.batch import BatchItem, process_batch
from app.services.catalog import load_catalog
from app.services.inbox import UnusableInput, load_requests
from app.services.intake import IntakeResult, IntakeService


def read_seed_file(path: Path) -> SeedFile:
    return SeedFile.model_validate_json(path.read_text(encoding="utf-8"))


async def seed(settings: Settings, items: Sequence[CatalogItem]) -> int:
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            return await load_catalog(session, items)
    finally:
        await engine.dispose()


async def process(
    settings: Settings, items: Sequence[BatchItem], unusable: Sequence[UnusableInput]
) -> list[IntakeResult]:
    engine = make_engine(settings.database_url)
    try:
        sessionmaker = make_sessionmaker(engine)
        provider = make_provider(settings)
        results = []
        async with sessionmaker() as session:
            service = IntakeService(session, provider, settings)
            for problem in unusable:
                results.append(
                    await service.record_unusable(
                        external_id=problem.external_id,
                        source_path=problem.source_path,
                        raw_text=problem.raw_text,
                        error=problem.error,
                    )
                )
        return results + await process_batch(sessionmaker, provider, settings, items)
    finally:
        await engine.dispose()


def print_report(results: Sequence[IntakeResult]) -> None:
    for result in results:
        draft = f" -> draft {result.draft_status}" if result.draft_status else ""
        error = f"  ({result.error})" if result.error else ""
        earlier = "  (already processed)" if result.already_processed else ""
        print(
            f"{result.external_id:<12} {result.order_ref:<8} {result.status}{draft}{error}{earlier}"
        )
    done_now = [result for result in results if not result.already_processed]
    statuses = Counter(result.status for result in done_now)
    # A later request can change a draft made earlier in the run (a conflict marks it
    # needs_review), so each new draft is counted by the last status reported for its order.
    final = {r.order_ref: r.draft_status for r in results if r.draft_status}
    new_drafts = Counter(final[r.order_ref] for r in done_now if r.status is RequestStatus.DRAFTED)
    print(
        f"\n{len(results)} requests: {statuses[RequestStatus.DRAFTED]} new drafts "
        f"({', '.join(f'{count} {status}' for status, count in new_drafts.items()) or 'none'}), "
        f"{statuses[RequestStatus.DUPLICATE]} duplicate, {statuses[RequestStatus.CONFLICT]} "
        f"conflict, {statuses[RequestStatus.FAILED]} failed, "
        f"{len(results) - len(done_now)} already processed"
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="order-intake")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="load the catalog from data/seed/seed.json into the database")
    process_parser = commands.add_parser(
        "process", help="process the seed requests and data/inbox (already processed: skipped)"
    )
    process_parser.add_argument(
        "--mode",
        choices=["live", "replay"],
        help="override MODEL_MODE: live calls the API and records replays, replay needs no key",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    if args.command == "seed":
        seed_file = read_seed_file(settings.seed_dir / "seed.json")
        count = asyncio.run(seed(settings, seed_file.catalog))
        print(f"Loaded {count} products into {settings.database_url}")
    elif args.command == "process":
        if args.mode:
            settings = settings.model_copy(update={"model_mode": args.mode})
        if settings.model_mode == "live" and settings.model_api_key is None:
            parser.error("MODEL_API_KEY is not set: add it to .env, or use --mode replay")
        items, unusable = load_requests(settings.seed_dir / "seed.json", settings.inbox_dir)
        print(f"Model mode: {settings.model_mode} ({settings.model_name})\n")
        print_report(asyncio.run(process(settings, items, unusable)))


if __name__ == "__main__":
    main()
