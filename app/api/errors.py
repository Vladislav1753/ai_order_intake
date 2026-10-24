from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.core.errors import (
    AlreadyExistsError,
    DomainError,
    InvalidDataError,
    NotFoundError,
    StorageUnavailableError,
)

STATUS_CODES: dict[type[DomainError], int] = {
    NotFoundError: 404,
    AlreadyExistsError: 409,
    InvalidDataError: 422,
    StorageUnavailableError: 503,
}


def register_error_handlers(app: FastAPI) -> None:
    """Domain errors raised while handling a request become an HTTP status with the message."""

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> PlainTextResponse:
        status = next((code for cls, code in STATUS_CODES.items() if isinstance(exc, cls)), 400)
        return PlainTextResponse(str(exc), status_code=status)
