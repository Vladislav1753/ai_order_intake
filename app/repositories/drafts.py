from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import DraftStatus
from app.db.errors import translates_db_errors
from app.models import DraftOrder


class DraftRepository:
    """Drafts always come back with their lines loaded (relationships are lazy="raise")."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, draft: DraftOrder) -> None:
        self.session.add(draft)

    @translates_db_errors
    async def get(self, draft_id: int) -> DraftOrder | None:
        return await self.session.scalar(
            select(DraftOrder)
            .where(DraftOrder.id == draft_id)
            .options(selectinload(DraftOrder.lines), selectinload(DraftOrder.corrections))
        )

    @translates_db_errors
    async def get_by_order_ref(self, order_ref: str) -> DraftOrder | None:
        return await self.session.scalar(
            select(DraftOrder)
            .where(DraftOrder.order_ref == order_ref)
            .options(selectinload(DraftOrder.lines))
        )

    @translates_db_errors
    async def list_reviewed(self) -> list[DraftOrder]:
        """Signed-off drafts with their lines and history, in sign-off order."""
        return list(
            await self.session.scalars(
                select(DraftOrder)
                .where(DraftOrder.status == DraftStatus.REVIEWED)
                .order_by(DraftOrder.reviewed_at, DraftOrder.id)
                .options(selectinload(DraftOrder.lines), selectinload(DraftOrder.corrections))
            )
        )

    @translates_db_errors
    async def list_all(self, status: DraftStatus | None = None) -> list[DraftOrder]:
        query = select(DraftOrder).order_by(DraftOrder.id).options(selectinload(DraftOrder.lines))
        if status is not None:
            query = query.where(DraftOrder.status == status)
        return list(await self.session.scalars(query))
