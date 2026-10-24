from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import PROJECT_ROOT, Settings
from app.core.enums import DraftStatus, FindingCode
from app.core.errors import InvalidDataError, NotFoundError
from app.db.session import make_sessionmaker
from app.models import DraftOrder
from app.repositories.drafts import DraftRepository
from app.schemas.review import LineCorrection
from app.schemas.seed import RequestIn, SeedFile
from app.services.catalog import load_catalog
from app.services.intake import IntakeService
from app.services.review import ReviewService
from tests.fakes import SEED_SCRIPTS, ScriptedProvider, answer, item, search

SEED = SeedFile.model_validate_json(
    (PROJECT_ROOT / "data" / "seed" / "seed.json").read_text(encoding="utf-8")
)
REQUESTS = {request.id: request for request in SEED.requests}
SETTINGS = Settings(_env_file=None)  # type: ignore[call-arg]

# R1's text, but the model cites a search that found nothing: its SKU is not backed.
UNBACKED = RequestIn(id="U1", order_ref="OU1", text="Please send 2 individual CAB-1 cables.")
CONFLICT = RequestIn(id="R1b", order_ref="O1", text="Change of plan: 3 CAB-1 cables please.")
SCRIPTS = {
    **SEED_SCRIPTS,
    "U1": [
        search("adapter"),
        answer(item("2 individual CAB-1 cables", "CAB-1", 2, query="adapter")),
    ],
}


@pytest.fixture
async def sessionmaker(migrated_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    sessionmaker = make_sessionmaker(migrated_engine)
    async with sessionmaker() as session:
        await load_catalog(session, SEED.catalog)
        service = IntakeService(session, ScriptedProvider(SCRIPTS), SETTINGS)
        for request in (REQUESTS["R1"], REQUESTS["R3"], UNBACKED):
            await service.process(request)
    return sessionmaker


async def draft_id(sessionmaker: async_sessionmaker[AsyncSession], order_ref: str) -> int:
    async with sessionmaker() as session:
        draft = await DraftRepository(session).get_by_order_ref(order_ref)
        assert draft is not None
        return draft.id


async def reload(sessionmaker: async_sessionmaker[AsyncSession], draft_id: int) -> DraftOrder:
    """Read the draft back in a new session, as a restarted app would."""
    async with sessionmaker() as session:
        draft = await DraftRepository(session).get(draft_id)
        assert draft is not None
        return draft


async def correct(
    sessionmaker: async_sessionmaker[AsyncSession], draft_id: int, field: str, value: Any
) -> DraftOrder:
    change = LineCorrection.model_validate({"line": 1, "field": field, "value": value})
    async with sessionmaker() as session:
        return await ReviewService(session).correct(draft_id, change)


def codes(draft: DraftOrder) -> list[str]:
    return [finding["code"] for finding in draft.findings]


async def test_a_correction_reruns_the_checks_and_is_saved_with_its_status_change(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    o3 = await draft_id(sessionmaker, "O3")  # "two boxes of the usual cable"

    await correct(sessionmaker, o3, "sku", "CAB-2")
    after_sku = await reload(sessionmaker, o3)
    await correct(sessionmaker, o3, "quantity", "2")
    draft = await reload(sessionmaker, o3)

    assert after_sku.status is DraftStatus.NEEDS_CLARIFICATION
    assert codes(after_sku) == [FindingCode.NON_INDIVIDUAL_UNIT]  # the box count is still open
    assert after_sku.clarification_text and "CAB-1" not in after_sku.clarification_text
    assert draft.status is DraftStatus.READY_FOR_REVIEW
    assert codes(draft) == []
    assert draft.clarification_text is None
    line = draft.lines[0]
    assert (line.sku, line.quantity, line.unit_cents, line.total_cents) == ("CAB-2", 2, 3000, 6000)
    assert (draft.subtotal_cents, draft.discount_cents, draft.total_cents) == (6000, 0, 6000)
    assert [
        (c.field, c.old_value, c.new_value, c.status_before, c.status_after)
        for c in draft.corrections
    ] == [
        ("sku", None, "CAB-2", DraftStatus.NEEDS_CLARIFICATION, DraftStatus.NEEDS_CLARIFICATION),
        ("quantity", None, "2", DraftStatus.NEEDS_CLARIFICATION, DraftStatus.READY_FOR_REVIEW),
    ]
    assert all(c.draft_line_id == line.id for c in draft.corrections)
    assert draft.proposal_json["lines"][0]["sku"] is None  # the model's proposal is kept as it was


async def test_clearing_a_sku_the_model_left_ambiguous_makes_it_ambiguous_again(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    o3 = await draft_id(sessionmaker, "O3")
    await correct(sessionmaker, o3, "sku", "CAB-1")

    draft = await correct(sessionmaker, o3, "sku", "")

    assert codes(draft) == [FindingCode.AMBIGUOUS_PRODUCT, FindingCode.NON_INDIVIDUAL_UNIT]
    assert draft.clarification_text and "CAB-1 (USB-C cable 1 m) or CAB-2" in (
        draft.clarification_text
    )


async def test_the_reviewer_setting_an_unbacked_lines_sku_clears_that_finding(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    ou1 = await draft_id(sessionmaker, "OU1")
    before = await reload(sessionmaker, ou1)

    draft = await correct(sessionmaker, ou1, "sku", "CAB-1")

    assert codes(before) == [FindingCode.UNVERIFIED_SKU, FindingCode.UNKNOWN_PRODUCT]
    assert draft.status is DraftStatus.READY_FOR_REVIEW
    assert draft.total_cents == 4000


async def test_a_conflict_stays_flagged_until_a_person_signs_the_draft_off(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        await IntakeService(session, ScriptedProvider({}), SETTINGS).process(CONFLICT)
    o1 = await draft_id(sessionmaker, "O1")

    corrected = await correct(sessionmaker, o1, "quantity", "3")
    async with sessionmaker() as session:
        await ReviewService(session).mark_reviewed(o1)
    reviewed = await reload(sessionmaker, o1)
    reopened = await correct(sessionmaker, o1, "quantity", "4")

    assert corrected.status is DraftStatus.NEEDS_REVIEW
    assert codes(corrected) == [FindingCode.CONFLICTING_REQUEST]
    assert corrected.total_cents == 6000
    assert reviewed.status is DraftStatus.REVIEWED
    assert reviewed.reviewed_at is not None
    assert (reviewed.corrections[-1].field, reviewed.corrections[-1].new_value) == (
        "status",
        "reviewed",
    )
    # Changing a signed-off draft needs a new sign-off.
    assert reopened.status is DraftStatus.NEEDS_REVIEW
    assert reopened.reviewed_at is None


async def test_a_draft_with_open_questions_cannot_be_signed_off(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    o3 = await draft_id(sessionmaker, "O3")
    async with sessionmaker() as session:
        with pytest.raises(InvalidDataError, match="needs clarification"):
            await ReviewService(session).mark_reviewed(o3)

    draft = await reload(sessionmaker, o3)
    assert draft.status is DraftStatus.NEEDS_CLARIFICATION
    assert draft.corrections == []


async def test_a_sku_outside_the_catalog_is_rejected_and_nothing_changes(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    o1 = await draft_id(sessionmaker, "O1")
    with pytest.raises(InvalidDataError, match="CAB-9 is not in the catalog"):
        await correct(sessionmaker, o1, "sku", "CAB-9")

    draft = await reload(sessionmaker, o1)
    assert draft.lines[0].sku == "CAB-1"
    assert draft.corrections == []


async def test_setting_the_value_a_line_already_has_saves_nothing(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    o1 = await draft_id(sessionmaker, "O1")

    await correct(sessionmaker, o1, "quantity", "2")

    assert (await reload(sessionmaker, o1)).corrections == []


async def test_a_missing_draft_or_line_is_not_found(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    o1 = await draft_id(sessionmaker, "O1")
    second_line = LineCorrection.model_validate({"line": 2, "field": "quantity", "value": "1"})
    async with sessionmaker() as session:
        with pytest.raises(NotFoundError, match="no line 2"):
            await ReviewService(session).correct(o1, second_line)
        with pytest.raises(NotFoundError, match="Draft 999 not found"):
            await ReviewService(session).mark_reviewed(999)
