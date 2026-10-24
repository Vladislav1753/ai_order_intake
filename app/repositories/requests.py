from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IncomingRequest


class RequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, request: IncomingRequest) -> None:
        self.session.add(request)

    async def get(self, request_id: int) -> IncomingRequest | None:
        return await self.session.get(IncomingRequest, request_id)

    async def get_by_external_id(self, external_id: str) -> IncomingRequest | None:
        return await self.session.scalar(
            select(IncomingRequest).where(IncomingRequest.external_id == external_id)
        )

    async def list_all(self) -> list[IncomingRequest]:
        return list(
            await self.session.scalars(select(IncomingRequest).order_by(IncomingRequest.id))
        )
