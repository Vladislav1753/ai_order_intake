import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import PROJECT_ROOT, Settings
from app.core.enums import DraftStatus, FindingCode, RequestStatus
from app.core.errors import StorageUnavailableError
from app.db.session import make_sessionmaker
from app.models import DraftOrder
from app.repositories.drafts import DraftRepository
from app.repositories.requests import RequestRepository
from app.schemas.seed import RequestIn, SeedFile
from app.services.batch import process_batch
from app.services.catalog import load_catalog
from app.services.intake import IntakeResult, IntakeService
from tests.fakes import SEED_SCRIPTS, ScriptedProvider

SEED = SeedFile.model_validate_json(
    (PROJECT_ROOT / "data" / "seed" / "seed.json").read_text(encoding="utf-8")
)
REQUESTS = {request.id: request for request in SEED.requests}
SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
async def sessionmaker(migrated_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    sessionmaker = make_sessionmaker(migrated_engine)
    async with sessionmaker() as session:
        await load_catalog(session, SEED.catalog)
    return sessionmaker


async def draft_count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(DraftOrder)) or 0


async def test_seed_requests_match_the_expected_results(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    items = [(request, f"seed.json#{request.id}") for request in SEED.requests]

    results = await process_batch(sessionmaker, ScriptedProvider(SEED_SCRIPTS), SETTINGS, items)

    assert [(r.external_id, r.status, r.draft_status) for r in results] == [
        ("R1", RequestStatus.DRAFTED, DraftStatus.READY_FOR_REVIEW),
        ("R2", RequestStatus.DRAFTED, DraftStatus.NEEDS_CLARIFICATION),
        ("R3", RequestStatus.DRAFTED, DraftStatus.NEEDS_CLARIFICATION),
        ("R4", RequestStatus.DUPLICATE, DraftStatus.READY_FOR_REVIEW),
    ]
    assert await draft_count(sessionmaker) == 3
    async with sessionmaker() as session:
        drafts = {draft.order_ref: draft for draft in await DraftRepository(session).list_all()}
    o1, o2, o3 = drafts["O1"], drafts["O2"], drafts["O3"]
    assert [(line.sku, line.quantity, line.total_cents) for line in o1.lines] == [
        ("CAB-1", 2, 4000)
    ]
    assert o1.total_cents == 4000
    assert [finding["code"] for finding in o2.findings] == [FindingCode.UNKNOWN_PRODUCT]
    assert o2.lines[0].sku is None
    assert o2.clarification_text and "Moon adapter" in o2.clarification_text
    assert [finding["code"] for finding in o3.findings] == [
        FindingCode.AMBIGUOUS_PRODUCT,
        FindingCode.NON_INDIVIDUAL_UNIT,
    ]
    assert (o3.lines[0].sku, o3.lines[0].quantity) == (None, None)
    assert o3.clarification_text and "CAB-1" in o3.clarification_text


async def test_reprocessing_a_request_changes_nothing(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    provider = ScriptedProvider(SEED_SCRIPTS)
    for _ in range(2):
        async with sessionmaker() as session:
            result = await IntakeService(session, provider, SETTINGS).process(REQUESTS["R1"])

    assert result.status is RequestStatus.DRAFTED
    assert result.already_processed
    assert len(provider.calls) == 2  # one search and one answer, from the first run only
    assert await draft_count(sessionmaker) == 1


async def test_different_text_for_the_same_order_is_a_conflict(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    provider = ScriptedProvider(SEED_SCRIPTS)
    changed = RequestIn(id="R1b", order_ref="O1", text="Actually, make it 3 CAB-1 cables.")
    async with sessionmaker() as session:
        await IntakeService(session, provider, SETTINGS).process(REQUESTS["R1"])
        result = await IntakeService(session, provider, SETTINGS).process(changed)

    assert result.status is RequestStatus.CONFLICT
    assert result.draft_status is DraftStatus.NEEDS_REVIEW
    assert await draft_count(sessionmaker) == 1


async def test_a_failed_request_does_not_stop_the_batch_and_can_be_retried(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    without_r2 = {key: value for key, value in SEED_SCRIPTS.items() if key != "R2"}
    items = [(request, None) for request in SEED.requests]

    results = await process_batch(sessionmaker, ScriptedProvider(without_r2), SETTINGS, items)

    assert (results[1].external_id, results[1].status) == ("R2", RequestStatus.FAILED)
    assert results[1].error and "no scripted reply" in results[1].error
    assert [result.status for result in results].count(RequestStatus.DRAFTED) == 2

    retry = await process_batch(sessionmaker, ScriptedProvider(SEED_SCRIPTS), SETTINGS, items)
    assert retry[1].status is RequestStatus.DRAFTED


async def test_unusable_input_is_kept_as_a_failed_request(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    for _ in range(2):  # idempotent: the second run updates the same row
        async with sessionmaker() as session:
            result = await IntakeService(session, ScriptedProvider({}), SETTINGS).record_unusable(
                external_id="unusable-bad.json-1234",
                source_path="data/inbox/bad.json",
                raw_text="{broken",
                error="Invalid JSON",
            )

    assert result.status is RequestStatus.FAILED
    assert result.error == "Unusable input: Invalid JSON"
    async with sessionmaker() as session:
        assert len(await RequestRepository(session).list_all()) == 1


async def test_a_database_error_fails_one_request_and_the_batch_goes_on(
    sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    process = IntakeService.process

    async def locked_for_r2(
        self: IntakeService, item: RequestIn, source_path: str | None = None
    ) -> IntakeResult:
        if item.id == "R2":
            raise StorageUnavailableError("Database unavailable: database is locked")
        return await process(self, item, source_path)

    monkeypatch.setattr(IntakeService, "process", locked_for_r2)
    items = [(request, None) for request in SEED.requests]

    results = await process_batch(sessionmaker, ScriptedProvider(SEED_SCRIPTS), SETTINGS, items)

    assert [result.status for result in results] == [
        RequestStatus.DRAFTED,
        RequestStatus.FAILED,
        RequestStatus.DRAFTED,
        RequestStatus.DUPLICATE,
    ]
    assert results[1].error == "Database unavailable: database is locked"
