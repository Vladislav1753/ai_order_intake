from http import HTTPStatus

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.schemas.export import ReviewedExport
from app.services.export import ExportService

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/reviewed.json", status_code=HTTPStatus.OK, response_model=ReviewedExport)
async def reviewed_orders(response: Response, session: SessionDep) -> ReviewedExport:
    """Every draft order a person signed off, as a JSON file."""
    response.headers["Content-Disposition"] = 'attachment; filename="reviewed-orders.json"'
    return await ExportService(session).reviewed()
