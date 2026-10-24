from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DraftOrder


class DraftRepository:
    """Drafts always come back with their lines loaded (relationships are lazy="raise")."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, draft: DraftOrder) -> None:
        self.session.add(draft)

    async def get(self, draft_id: int) -> DraftOrder | None:
        return await self.session.scalar(
            select(DraftOrder)
            .where(DraftOrder.id == draft_id)
            .options(selectinload(DraftOrder.lines), selectinload(DraftOrder.corrections))
        )

    async def get_by_order_ref(self, order_ref: str) -> DraftOrder | None:
        return await self.session.scalar(
            select(DraftOrder)
            .where(DraftOrder.order_ref == order_ref)
            .options(selectinload(DraftOrder.lines))
        )

    async def list_all(self) -> list[DraftOrder]:
        return list(
            await self.session.scalars(
                select(DraftOrder).order_by(DraftOrder.id).options(selectinload(DraftOrder.lines))
            )
        )
