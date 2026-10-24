"""Process many requests: order groups run concurrently, each group in input order."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.enums import RequestStatus
from app.core.errors import DomainError
from app.providers.base import LLMProvider
from app.schemas.seed import RequestIn
from app.services.intake import IntakeResult, IntakeService

log = logging.getLogger(__name__)

BatchItem = tuple[RequestIn, str | None]  # request and the file it came from


async def process_batch(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: LLMProvider,
    settings: Settings,
    items: Sequence[BatchItem],
) -> list[IntakeResult]:
    """Results come back in input order.

    Requests sharing an `order_ref` run one after another, so dedupe sees the earlier draft;
    different orders run in parallel, at most `max_concurrency` groups at a time.
    """
    groups: defaultdict[str, list[int]] = defaultdict(list)
    for index, (item, _) in enumerate(items):
        groups[item.order_ref].append(index)
    results: dict[int, IntakeResult] = {}
    semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def run_group(indexes: list[int]) -> None:
        async with semaphore:
            for index in indexes:
                item, source_path = items[index]
                results[index] = await _process_one(
                    sessionmaker, provider, settings, item, source_path
                )

    async with asyncio.TaskGroup() as group_tasks:
        for indexes in groups.values():
            group_tasks.create_task(run_group(indexes))
    return [results[index] for index in range(len(items))]


async def _process_one(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: LLMProvider,
    settings: Settings,
    item: RequestIn,
    source_path: str | None,
) -> IntakeResult:
    """One request in its own session. No failure here stops the rest of the batch."""
    try:
        async with sessionmaker() as session:
            return await IntakeService(session, provider, settings).process(item, source_path)
    except DomainError as exc:
        log.warning("request %s failed: %s", item.id, exc)
        error = str(exc)
    except Exception as exc:
        log.exception("request %s crashed", item.id)  # a bug: keep the traceback
        error = f"unexpected {type(exc).__name__}: {exc}"
    return IntakeResult(
        external_id=item.id, order_ref=item.order_ref, status=RequestStatus.FAILED, error=error
    )
