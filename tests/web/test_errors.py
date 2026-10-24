import pytest
from httpx2 import ASGITransport, AsyncClient

from app.core.errors import (
    AlreadyExistsError,
    DomainError,
    InvalidDataError,
    NotFoundError,
    StorageUnavailableError,
)
from app.main import create_app


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (NotFoundError("Draft 9 not found"), 404),
        (AlreadyExistsError("Already saved"), 409),
        (InvalidDataError("Rejected"), 422),
        (StorageUnavailableError("Database unavailable"), 503),
    ],
)
async def test_domain_errors_become_http_statuses(error: DomainError, status: int) -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise error

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == status
    assert response.text == str(error)
