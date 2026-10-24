from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RequestStatus
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
    async def list_by_order_ref(self, order_ref: str) -> list[IncomingRequest]:
        return list(
            await self.session.scalars(
                select(IncomingRequest)
                .where(IncomingRequest.order_ref == order_ref)
                .order_by(IncomingRequest.id)
            )
        )

    @translates_db_errors
    async def list_all(self, status: RequestStatus | None = None) -> list[IncomingRequest]:
        query = select(IncomingRequest).order_by(IncomingRequest.id)
        if status is not None:
            query = query.where(IncomingRequest.status == status)
        return list(await self.session.scalars(query))
