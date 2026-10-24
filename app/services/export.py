"""Signed-off drafts as structured data, for whatever system takes the orders on from here."""

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Correction, DraftOrder, IncomingRequest
from app.repositories.drafts import DraftRepository
from app.repositories.requests import RequestRepository
from app.schemas.export import ExportedChange, ExportedOrder, ReviewedExport
from app.utils.time import utcnow


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.drafts = DraftRepository(session)
        self.requests = RequestRepository(session)

    async def reviewed(self) -> ReviewedExport:
        """Only drafts a person marked reviewed: passing the checks alone is not enough."""
        by_order: defaultdict[str, list[IncomingRequest]] = defaultdict(list)
        for request in await self.requests.list_all():
            if request.order_ref:
                by_order[request.order_ref].append(request)
        return ReviewedExport(
            exported_at=utcnow(),
            orders=[
                _order(draft, by_order[draft.order_ref])
                for draft in await self.drafts.list_reviewed()
            ],
        )


def _order(draft: DraftOrder, requests: Sequence[IncomingRequest]) -> ExportedOrder:
    positions = {line.id: line.position for line in draft.lines}
    source = next(r for r in requests if r.id == draft.source_request_id)
    return ExportedOrder.model_validate(
        {
            "order_ref": draft.order_ref,
            "source_request": source.external_id,
            "later_requests": [r.external_id for r in requests if r.id != source.id],
            "reviewed_at": draft.reviewed_at,
            "lines": draft.lines,
            "subtotal_cents": draft.subtotal_cents,
            "discount_cents": draft.discount_cents,
            "total_cents": draft.total_cents,
            "findings": draft.findings,
            "history": [_change(correction, positions) for correction in draft.corrections],
        }
    )


def _change(correction: Correction, positions: dict[int, int]) -> ExportedChange:
    line_id = correction.draft_line_id
    return ExportedChange(
        at=correction.created_at,
        line=None if line_id is None else positions[line_id],
        field=correction.field,
        old_value=correction.old_value,
        new_value=correction.new_value,
        status_before=correction.status_before,
        status_after=correction.status_after,
    )
