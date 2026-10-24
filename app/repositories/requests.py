from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.errors import translates_db_errors
from app.models import IncomingRequest


class RequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, request: IncomingRequest) -> None:
        self.session.add(request)

    @translates_db_errors
    async def get(self, request_id: int) -> IncomingRequest | None:
        return await self.session.get(IncomingRequest, request_id)

    @translates_db_errors
    async def get_by_external_id(self, external_id: str) -> IncomingRequest | None:
        return await self.session.scalar(
            select(IncomingRequest).where(IncomingRequest.external_id == external_id)
        )

    @translates_db_errors
    async def list_all(self) -> list[IncomingRequest]:
        return list(
            await self.session.scalars(select(IncomingRequest).order_by(IncomingRequest.id))
        )
