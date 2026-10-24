"""The committed replays/ reproduce the recorded real run, with no API key and no network.

If this fails with "no saved response", the prompt, schemas, or catalog changed since the
replays were recorded: re-record with `just record` on a fresh database.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import PROJECT_ROOT, Settings
from app.core.enums import DraftStatus, RequestStatus, ResponseSource
from app.db.session import make_sessionmaker
from app.providers.factory import make_provider
from app.repositories.requests import RequestRepository
from app.schemas.seed import SeedFile
from app.services.batch import process_batch
from app.services.catalog import load_catalog

SEED = SeedFile.model_validate_json(
    (PROJECT_ROOT / "data" / "seed" / "seed.json").read_text(encoding="utf-8")
)


async def test_seed_requests_replay_from_saved_real_responses(
    migrated_engine: AsyncEngine,
) -> None:
    settings = Settings(_env_file=None, model_mode="replay")  # type: ignore[call-arg]
    assert settings.model_api_key is None
    sessionmaker = make_sessionmaker(migrated_engine)
    async with sessionmaker() as session:
        await load_catalog(session, SEED.catalog)

    results = await process_batch(
        sessionmaker, make_provider(settings), settings, [(r, None) for r in SEED.requests]
    )

    assert [(r.external_id, r.status, r.draft_status) for r in results] == [
        ("R1", RequestStatus.DRAFTED, DraftStatus.READY_FOR_REVIEW),
        ("R2", RequestStatus.DRAFTED, DraftStatus.NEEDS_CLARIFICATION),
        ("R3", RequestStatus.DRAFTED, DraftStatus.NEEDS_CLARIFICATION),
        ("R4", RequestStatus.DUPLICATE, DraftStatus.READY_FOR_REVIEW),
    ]
    async with sessionmaker() as session:
        requests = await RequestRepository(session).list_all()
    sources = {call["source"] for request in requests for call in request.model_calls}
    assert sources == {ResponseSource.CACHED}
