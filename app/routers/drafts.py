from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.deps import SessionDep
from app.api.templates import templates
from app.schemas.review import LineCorrection
from app.services.queue import QueueService
from app.services.review import ReviewService

# Rejected changes are shown on the draft page by app/api/handlers.py.
router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("/{draft_id}", status_code=HTTPStatus.OK, response_class=HTMLResponse)
async def draft_detail(request: Request, draft_id: int, session: SessionDep) -> HTMLResponse:
    detail = await QueueService(session).draft_detail(draft_id)
    return templates.TemplateResponse(request, "draft.html", {"detail": detail})


@router.post(
    "/{draft_id}/corrections", status_code=HTTPStatus.SEE_OTHER, response_class=RedirectResponse
)
async def correct_line(
    draft_id: int, change: Annotated[LineCorrection, Form()], session: SessionDep
) -> str:
    """Correct one field of one line; the checks re-run and the change is logged. Redirects
    back to the draft page."""
    await ReviewService(session).correct(draft_id, change)
    return f"/drafts/{draft_id}"


@router.post(
    "/{draft_id}/review", status_code=HTTPStatus.SEE_OTHER, response_class=RedirectResponse
)
async def mark_reviewed(draft_id: int, session: SessionDep) -> str:
    """Sign the draft off. Redirects back to the draft page."""
    await ReviewService(session).mark_reviewed(draft_id)
    return f"/drafts/{draft_id}"
