import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DraftStatus
from app.core.errors import AlreadyExistsError, InvalidDataError
from app.db.errors import translate_db_errors
from app.models import DraftLine, DraftOrder, IncomingRequest
from app.repositories.drafts import DraftRepository
from app.repositories.products import ProductRepository
from app.repositories.requests import RequestRepository
from app.schemas.seed import CatalogItem
from app.services.catalog import load_catalog

CATALOG = [
    CatalogItem(sku="CAB-1", name="USB-C cable 1 m", unit_cents=2000),
    CatalogItem(sku="HUB-1", name="USB hub", unit_cents=5000),
]


async def test_load_catalog_is_idempotent_and_updates_by_sku(session: AsyncSession) -> None:
    await load_catalog(session, CATALOG)
    await load_catalog(session, [CatalogItem(sku="CAB-1", name="USB-C cable 1 m", unit_cents=2100)])

    products = await ProductRepository(session).list_all()

    assert [(p.sku, p.unit_cents) for p in products] == [("CAB-1", 2100), ("HUB-1", 5000)]


async def test_request_lookup_by_external_id(session: AsyncSession) -> None:
    requests = RequestRepository(session)
    requests.add(IncomingRequest(external_id="R1", order_ref="O1", text="t", content_hash="h"))
    await session.commit()

    found = await requests.get_by_external_id("R1")

    assert found is not None and found.order_ref == "O1"
    assert await requests.get_by_external_id("R9") is None


async def test_duplicate_external_id_is_a_domain_error(session: AsyncSession) -> None:
    requests = RequestRepository(session)
    requests.add(IncomingRequest(external_id="R1", order_ref="O1", text="t", content_hash="h"))
    requests.add(IncomingRequest(external_id="R1", order_ref="O2", text="t", content_hash="h"))

    # The query autoflushes the pending inserts, so the violation surfaces here.
    with pytest.raises(AlreadyExistsError, match=r"requests\.external_id"):
        await requests.get_by_external_id("R1")


async def test_sku_outside_the_catalog_is_a_domain_error(session: AsyncSession) -> None:
    request = IncomingRequest(external_id="R1", order_ref="O1", text="t", content_hash="h")
    session.add(request)
    await session.flush()
    session.add(
        DraftOrder(
            order_ref="O1",
            source_request_id=request.id,
            status=DraftStatus.READY_FOR_REVIEW,
            proposal_json={},
            lines=[DraftLine(position=1, customer_text="2 CAB-9", sku="CAB-9", quantity=2)],
        )
    )

    with pytest.raises(InvalidDataError, match="FOREIGN KEY"), translate_db_errors():
        await session.commit()


async def test_draft_by_order_ref_comes_with_lines_loaded(session: AsyncSession) -> None:
    await load_catalog(session, CATALOG)
    request = IncomingRequest(external_id="R1", order_ref="O1", text="t", content_hash="h")
    session.add(request)
    await session.flush()
    draft = DraftOrder(
        order_ref="O1",
        source_request_id=request.id,
        status=DraftStatus.READY_FOR_REVIEW,
        proposal_json={},
        lines=[DraftLine(position=1, customer_text="2 CAB-1", sku="CAB-1", quantity=2)],
    )
    DraftRepository(session).add(draft)
    await session.commit()
    session.expunge_all()  # force a real reload instead of the identity map

    loaded = await DraftRepository(session).get_by_order_ref("O1")

    assert loaded is not None
    assert [(line.sku, line.quantity) for line in loaded.lines] == [("CAB-1", 2)]
    assert loaded.findings == []
