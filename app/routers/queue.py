from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.api.deps import SessionDep
from app.api.templates import templates
from app.services.queue import QUEUE_FILTERS, QueueFilter, QueueService

router = APIRouter(tags=["queue"])


@router.get("/", response_class=HTMLResponse)
async def queue(
    request: Request, session: SessionDep, status: QueueFilter | None = None
) -> HTMLResponse:
    service = QueueService(session)
    return templates.TemplateResponse(
        request,
        "queue.html",
        {
            "summary": await service.summary(),
            "items": await service.items(status),
            "status": status,
            "filters": QUEUE_FILTERS,
        },
    )


@router.get("/requests/{request_id}", response_class=HTMLResponse)
async def request_detail(request: Request, request_id: int, session: SessionDep) -> HTMLResponse:
    detail = await QueueService(session).request_detail(request_id)
    return templates.TemplateResponse(request, "request.html", {"detail": detail})
