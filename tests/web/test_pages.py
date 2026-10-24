"""The review screens, on a database processed from the committed replays (no key needed)."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx2 import AsyncClient

from app.cli import process, read_seed_file, seed
from app.core.config import Settings
from app.db.session import make_engine, make_sessionmaker
from app.repositories.drafts import DraftRepository
from app.repositories.requests import RequestRepository
from app.services.inbox import load_requests
from tests.client import app_client
from tests.integration.conftest import run_alembic


@pytest.fixture
async def settings(tmp_path: Path) -> Settings:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'pages.db').as_posix()}"
    settings = Settings(_env_file=None, model_mode="replay", database_url=url)  # type: ignore[call-arg]
    engine = make_engine(url)
    await run_alembic(engine, "upgrade", "head")
    await engine.dispose()
    await seed(settings, read_seed_file(settings.seed_dir / "seed.json").catalog)
    await process(settings, *load_requests(settings.seed_dir / "seed.json", settings.inbox_dir))
    return settings


@pytest.fixture
async def pages(settings: Settings) -> AsyncIterator[AsyncClient]:
    async with app_client(settings) as client:
        yield client


async def ids(settings: Settings) -> tuple[dict[str, int], dict[str, int]]:
    """Draft id per order_ref and request id per external id."""
    engine = make_engine(settings.database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            drafts = {d.order_ref: d.id for d in await DraftRepository(session).list_all()}
            requests = {r.external_id: r.id for r in await RequestRepository(session).list_all()}
    finally:
        await engine.dispose()
    return drafts, requests


def rows(html: str) -> int:
    return len(re.findall(r"<tr>\s*<td><span class=\"badge", html))


async def test_the_queue_counts_orders_apart_from_duplicates(pages: AsyncClient) -> None:
    response = await pages.get("/")

    assert response.status_code == 200
    assert "14 requests received → 10 draft orders" in response.text
    assert "1 duplicate and 1 conflicting" in response.text
    assert rows(response.text) == 12  # 10 drafts and 2 failed requests


async def test_the_status_filter_shows_only_that_status(pages: AsyncClient) -> None:
    failed = await pages.get("/", params={"status": "failed"})
    unclear = await pages.get("/", params={"status": "needs_clarification"})
    bad = await pages.get("/", params={"status": "maybe"})

    assert rows(failed.text) == 2
    assert "Unusable input file" in failed.text and "Model call failed" in failed.text
    assert rows(unclear.text) == 5
    assert "Ready for review</span></td>" not in unclear.text
    assert bad.status_code == 422


async def test_a_draft_shows_the_request_beside_the_proposal(
    pages: AsyncClient, settings: Settings
) -> None:
    drafts, _ = await ids(settings)

    response = await pages.get(f"/drafts/{drafts['O12']}")

    assert response.status_code == 200
    assert "10 USB-C cables" in response.text  # the original email
    assert "Matches: CAB-1 (USB-C cable 1 m), CAB-2 (USB-C cable 2 m)." in response.text
    assert "Ambiguous product" in response.text
    assert "Which one do you need?" in response.text  # the clarification draft
    assert "2 cached" in response.text  # replayed responses are labelled
    assert "No corrections yet" in response.text


async def test_a_correction_from_the_form_is_saved_and_shown(
    pages: AsyncClient, settings: Settings
) -> None:
    drafts, _ = await ids(settings)
    url = f"/drafts/{drafts['O12']}"

    saved = await pages.post(
        f"{url}/corrections", data={"line": 1, "field": "sku", "value": "CAB-2"}
    )
    page = await pages.get(url)

    assert saved.status_code == 303
    assert saved.headers["location"] == url
    assert "Ready for review" in page.text
    assert "$270.00" in page.text
    assert "Line 1 sku: empty → CAB-2" in page.text
    assert "No questions for the customer." in page.text


async def test_a_rejected_correction_is_explained_and_not_saved(
    pages: AsyncClient, settings: Settings
) -> None:
    drafts, _ = await ids(settings)
    url = f"/drafts/{drafts['O12']}"

    zero = await pages.post(f"{url}/corrections", data={"line": 1, "field": "quantity", "value": 0})
    unknown = await pages.post(f"{url}/corrections", data={"line": 1, "field": "sku", "value": "X"})
    sign_off = await pages.post(f"{url}/review")

    assert zero.status_code == 422
    assert "Not saved." in zero.text and "positive whole number" in zero.text
    assert zero.headers["hx-push-url"] == url  # the address bar keeps the draft's URL
    assert unknown.status_code == 422 and "X is not in the catalog" in unknown.text
    assert sign_off.status_code == 422 and "still needs clarification" in sign_off.text
    assert "No corrections yet" in (await pages.get(url)).text


async def test_signing_off_a_ready_draft(pages: AsyncClient, settings: Settings) -> None:
    drafts, _ = await ids(settings)
    url = f"/drafts/{drafts['O1']}"

    response = await pages.post(f"{url}/review")
    page = await pages.get(url)

    assert response.status_code == 303
    assert "Marked reviewed" in page.text
    assert "signed off" in page.text


async def test_a_failed_request_shows_its_labelled_model_calls(
    pages: AsyncClient, settings: Settings
) -> None:
    _, requests = await ids(settings)

    simulated = await pages.get(f"/requests/{requests['R11']}")
    duplicate = await pages.get(f"/requests/{requests['R4']}")

    assert "Model call failed." in simulated.text
    assert 'class="badge src-simulated-failure">simulated-failure</span></td>' in simulated.text
    assert "before any model call" in duplicate.text


async def test_unknown_ids_are_not_found(pages: AsyncClient) -> None:
    assert (await pages.get("/drafts/999")).status_code == 404
    assert (await pages.get("/requests/999")).status_code == 404
    response = await pages.post("/drafts/999/corrections", data={"line": 1, "field": "sku"})
    assert response.status_code == 404
