from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from app.api.deps import SessionDep
from app.api.templates import templates
from app.core.errors import InvalidDataError
from app.schemas.review import LineCorrection
from app.services.queue import QueueService
from app.services.review import ReviewService

router = APIRouter(prefix="/drafts", tags=["drafts"])


@router.get("/{draft_id}", response_class=HTMLResponse)
async def draft_detail(request: Request, draft_id: int, session: SessionDep) -> HTMLResponse:
    return await _render(request, session, draft_id)


@router.post("/{draft_id}/corrections")
async def correct_line(
    request: Request,
    draft_id: int,
    session: SessionDep,
    line: Annotated[int, Form()],
    field: Annotated[str, Form()],
    value: Annotated[str, Form()] = "",
) -> Response:
    """Correct one field of one line; the checks re-run and the change is logged."""
    try:
        change = LineCorrection.model_validate({"line": line, "field": field, "value": value})
        await ReviewService(session).correct(draft_id, change)
    except ValidationError as exc:
        message = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        return await _render(request, session, draft_id, error=message)
    except InvalidDataError as exc:
        return await _render(request, session, draft_id, error=str(exc))
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


@router.post("/{draft_id}/review")
async def mark_reviewed(request: Request, draft_id: int, session: SessionDep) -> Response:
    try:
        await ReviewService(session).mark_reviewed(draft_id)
    except InvalidDataError as exc:
        return await _render(request, session, draft_id, error=str(exc))
    return RedirectResponse(f"/drafts/{draft_id}", status_code=303)


async def _render(
    request: Request, session: SessionDep, draft_id: int, error: str | None = None
) -> HTMLResponse:
    """The detail page; with `error`, the rejected change is reported and nothing was saved.

    The error page answers a POST, so it tells htmx to show the draft's own URL, not the
    form's, in the address bar.
    """
    detail = await QueueService(session).draft_detail(draft_id)
    return templates.TemplateResponse(
        request,
        "draft.html",
        {"detail": detail, "error": error},
        status_code=422 if error else 200,
        headers={"HX-Push-Url": f"/drafts/{draft_id}"} if error else None,
    )
