from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DraftStatus
from app.models import DraftLine, DraftOrder, IncomingRequest, Product


async def _draft(session: AsyncSession) -> DraftOrder:
    session.add(Product(sku="CAB-1", name="USB-C cable 1 m", unit_cents=2000))
    request = IncomingRequest(external_id="R1", order_ref="O1", text="t", content_hash="h")
    session.add(request)
    await session.flush()
    draft = DraftOrder(
        order_ref="O1",
        source_request_id=request.id,
        status=DraftStatus.READY_FOR_REVIEW,
        proposal_json={},
    )
    session.add(draft)
    await session.flush()
    return draft


async def test_timestamps_come_back_timezone_aware(session: AsyncSession) -> None:
    draft_id = (await _draft(session)).id
    await session.commit()
    session.expire_all()  # attributes of expired objects can't be read without awaiting a reload

    loaded = await session.get(DraftOrder, draft_id)

    assert loaded is not None
    assert loaded.created_at.tzinfo == UTC
    assert loaded.created_at <= datetime.now(UTC)


async def test_order_ref_is_unique_per_draft(session: AsyncSession) -> None:
    await _draft(session)
    other = IncomingRequest(external_id="R4", order_ref="O1", text="t", content_hash="h")
    session.add(other)
    await session.flush()
    session.add(
        DraftOrder(
            order_ref="O1",
            source_request_id=other.id,
            status=DraftStatus.READY_FOR_REVIEW,
            proposal_json={},
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_line_sku_must_exist_in_catalog(session: AsyncSession) -> None:
    draft = await _draft(session)
    session.add(DraftLine(draft_order_id=draft.id, position=1, customer_text="x", sku="MOON-1"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_line_quantity_must_be_positive(session: AsyncSession) -> None:
    draft = await _draft(session)
    session.add(DraftLine(draft_order_id=draft.id, position=1, customer_text="x", quantity=0))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_unloaded_relationship_raises_instead_of_querying(session: AsyncSession) -> None:
    draft_id = (await _draft(session)).id
    await session.commit()
    session.expire_all()
    loaded = await session.get(DraftOrder, draft_id)
    assert loaded is not None

    # Repositories must eager-load (selectinload); a hidden lazy load would fail in async.
    with pytest.raises(Exception, match="lazy='raise'"):
        _ = loaded.lines
