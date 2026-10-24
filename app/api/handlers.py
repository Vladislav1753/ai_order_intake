"""Exception handlers: errors become responses here, so routers only call services.

A change rejected on the draft page (a form POST under /drafts/{draft_id}/) shows that page
again with the reason, status 422, and nothing saved. Any other domain error becomes its
HTTP status with the message as text; other invalid input gets FastAPI's default 422.
"""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, Response

from app.api.templates import templates
from app.core.errors import (
    AlreadyExistsError,
    DomainError,
    InvalidDataError,
    NotFoundError,
    StorageUnavailableError,
)
from app.services.queue import QueueService

STATUS_CODES: dict[type[DomainError], HTTPStatus] = {
    NotFoundError: HTTPStatus.NOT_FOUND,
    AlreadyExistsError: HTTPStatus.CONFLICT,
    InvalidDataError: HTTPStatus.UNPROCESSABLE_ENTITY,
    StorageUnavailableError: HTTPStatus.SERVICE_UNAVAILABLE,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> Response:
        status = next(
            (code for cls, code in STATUS_CODES.items() if isinstance(exc, cls)),
            HTTPStatus.BAD_REQUEST,
        )
        page = await _draft_page(request, str(exc)) if isinstance(exc, InvalidDataError) else None
        return page or PlainTextResponse(str(exc), status_code=status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> Response:
        page = await _draft_page(request, _messages(exc))
        return page or await request_validation_exception_handler(request, exc)


async def _draft_page(request: Request, error: str) -> Response | None:
    """The draft page with the rejection reason, for the draft page's own forms only."""
    if request.method != "POST" or not request.url.path.startswith("/drafts/"):
        return None
    try:
        draft_id = int(request.path_params["draft_id"])
        async with request.app.state.sessionmaker() as session:
            detail = await QueueService(session).draft_detail(draft_id)
    except (KeyError, ValueError, NotFoundError):
        return None
    return templates.TemplateResponse(
        request,
        "draft.html",
        {"detail": detail, "error": error},
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        # The page answers a POST: keep the draft's own URL in the address bar (htmx).
        headers={"HX-Push-Url": f"/drafts/{draft_id}"},
    )


def _messages(exc: RequestValidationError) -> str:
    """Pydantic's messages, named by field when the error belongs to one."""
    messages = []
    for error in exc.errors():
        message = str(error["msg"]).removeprefix("Value error, ")
        field = error["loc"][-1] if len(error["loc"]) > 1 else None
        messages.append(f"{field}: {message}" if field else message)
    return "; ".join(messages)
