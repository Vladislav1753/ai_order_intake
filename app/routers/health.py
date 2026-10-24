from http import HTTPStatus

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", status_code=HTTPStatus.OK, response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", model_mode=get_settings().model_mode)
