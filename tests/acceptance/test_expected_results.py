"""The brief's minimum demonstration: every input processed from the committed replays (no
API key, no network) must match data/expected/expected-results.json, which was derived by
hand from the rules and checked by scripts/check_expected.py, never copied from app output.
"""

import json
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from app.cli import process, read_seed_file, seed
from app.core.config import PROJECT_ROOT, Settings
from app.db.session import make_engine, make_sessionmaker
from app.models import DraftOrder, IncomingRequest
from app.repositories.drafts import DraftRepository
from app.repositories.requests import RequestRepository
from app.services.inbox import load_requests
from tests.client import app_client
from tests.integration.conftest import run_alembic

EXPECTED: dict[str, Any] = json.loads(
    (PROJECT_ROOT / "data" / "expected" / "expected-results.json").read_text(encoding="utf-8")
)


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[str]:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'acceptance.db').as_posix()}"
    engine = make_engine(url)
    await run_alembic(engine, "upgrade", "head")
    await engine.dispose()
    yield url


async def process_everything(
    database_url: str,
) -> tuple[dict[str, IncomingRequest], dict[str, DraftOrder]]:
    """Seed and process every input exactly as `just seed` + `just process` do."""
    settings = Settings(_env_file=None, model_mode="replay", database_url=database_url)  # type: ignore[call-arg]
    assert settings.model_api_key is None
    seed_file = read_seed_file(settings.seed_dir / "seed.json")
    await seed(settings, seed_file.catalog)
    items, unusable = load_requests(settings.seed_dir / "seed.json", settings.inbox_dir)
    await process(settings, items, unusable)

    engine = make_engine(database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            requests = await RequestRepository(session).list_all()
            drafts = await DraftRepository(session).list_all()
    finally:
        await engine.dispose()
    by_id = {}
    for request in requests:
        # An unusable file has no id of its own; match it by its source file instead.
        key = request.external_id
        if key.startswith("unusable-"):
            key = next(c["id"] for c in EXPECTED["requests"] if c["source"] == request.source_path)
        by_id[key] = request
    return by_id, {draft.order_ref: draft for draft in drafts}


def mismatches(
    case: dict[str, Any], request: IncomingRequest | None, draft: DraftOrder | None
) -> list[str]:
    if request is None:
        return ["request not stored"]
    problems = []
    if request.status != case["request_status"]:
        problems.append(f"request {request.status} != {case['request_status']}")
    if "model_call_source" in case:
        sources = [call.get("source") for call in request.model_calls]
        if case["model_call_source"] not in sources:
            problems.append(f"model call sources {sources}")
    if "draft_status" not in case:
        return problems
    if draft is None:
        return [*problems, "no draft"]
    if draft.status != case["draft_status"]:
        problems.append(f"draft {draft.status} != {case['draft_status']}")
    codes = [finding["code"] for finding in draft.findings]
    if codes != case["findings"]:
        problems.append(f"findings {codes} != {case['findings']}")
    if "total_cents" in case and draft.total_cents != case["total_cents"]:
        problems.append(f"total {draft.total_cents} != {case['total_cents']}")
    if len(draft.lines) != len(case["lines"]):
        return [*problems, f"{len(draft.lines)} lines != {len(case['lines'])}"]
    proposed = draft.proposal_json["lines"]
    for number, (line, expected, proposal) in enumerate(
        zip(draft.lines, case["lines"], proposed, strict=True), start=1
    ):
        observed = {
            "sku": line.sku,
            "quantity": line.quantity,
            "unit": line.unit_label,
            "unit_cents": line.unit_cents,
            "line_cents": line.line_cents,
            "discount_cents": line.discount_cents,
            "total_cents": line.total_cents,
            "candidates": [hit["sku"] for hit in proposal["candidates"]],
        }
        problems += [
            f"line {number} {field} {observed[field]} != {value}"
            for field, value in expected.items()
            if observed[field] != value
        ]
    return problems


async def test_every_input_matches_the_expected_results(
    database: str,
) -> None:
    requests, drafts = await process_everything(database)

    report = {
        case["id"]: mismatches(case, requests.get(case["id"]), drafts.get(case["order_ref"]))
        for case in EXPECTED["requests"]
    }

    failed = {request_id: problems for request_id, problems in report.items() if problems}
    assert not failed, json.dumps(failed, indent=2)


async def test_counts_match_and_duplicates_are_not_new_orders(
    database: str,
) -> None:
    requests, drafts = await process_everything(database)
    expected = EXPECTED["aggregates"]

    assert len(requests) == expected["requests"]
    assert dict(Counter(r.status.value for r in requests.values())) == expected["request_status"]
    assert len(drafts) == expected["drafts"]
    assert (
        dict(Counter(d.status.value for d in drafts.values()))
        == expected["draft_status_after_processing"]
    )


async def test_reprocessing_everything_creates_nothing_new(
    database: str,
) -> None:
    await process_everything(database)
    requests, drafts = await process_everything(database)

    assert len(requests) == EXPECTED["aggregates"]["requests"]
    assert len(drafts) == EXPECTED["aggregates"]["drafts"]


async def test_reviewer_correction_c1(database: str) -> None:
    """C1 through the review screen, then a restart: the saved draft, its re-run checks and
    the history entry must match the independently priced expectation."""
    _, drafts = await process_everything(database)
    case = EXPECTED["corrections"][0]
    draft_id = drafts[case["order_ref"]].id
    change = case["change"]
    settings = Settings(_env_file=None, model_mode="replay", database_url=database)  # type: ignore[call-arg]

    async with app_client(settings) as client:
        saved = await client.post(
            f"/drafts/{draft_id}/corrections",
            data={"line": change["line"], "field": change["field"], "value": change["to"]},
        )
    async with app_client(settings) as client:  # restarted
        page = await client.get(f"/drafts/{draft_id}")

    assert saved.status_code == 303
    assert page.status_code == 200
    assert f"Line {change['line']} {change['field']}: empty → {change['to']}" in page.text
    engine = make_engine(database)
    try:
        async with make_sessionmaker(engine)() as session:
            draft = await DraftRepository(session).get(draft_id)
            statuses = Counter(d.status.value for d in await DraftRepository(session).list_all())
    finally:
        await engine.dispose()
    assert draft is not None
    fields = ("sku", "quantity", "unit_cents", "line_cents", "discount_cents", "total_cents")
    assert [{f: getattr(line, f) for f in fields} for line in draft.lines] == case["lines_after"]
    assert (draft.subtotal_cents, draft.discount_cents, draft.total_cents) == (
        case["subtotal_cents"],
        case["discount_cents"],
        case["total_cents"],
    )
    assert draft.status == case["status_after"]
    assert draft.findings == []
    assert draft.proposal_json["lines"][0]["sku"] == change["from"]  # the proposal is kept
    (history,) = draft.corrections
    assert (history.field, history.old_value, history.new_value) == (
        change["field"],
        change["from"],
        change["to"],
    )
    assert (history.status_before, history.status_after) == (
        case["status_before"],
        case["status_after"],
    )
    assert dict(statuses) == EXPECTED["aggregates"]["draft_status_after_corrections"]
