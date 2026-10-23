"""Every model is imported here so that `Base.metadata` sees all tables (Alembic relies on it)."""

from app.models.draft import Correction, DraftLine, DraftOrder
from app.models.product import Product
from app.models.request import IncomingRequest

__all__ = ["Correction", "DraftLine", "DraftOrder", "IncomingRequest", "Product"]
