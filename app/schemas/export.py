"""The reviewed-orders export: drafts a person signed off, as plain JSON."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.enums import DraftStatus
from app.schemas.draft import Finding


class ExportedLine(BaseModel):
    """A priced line. Sign-off is refused while a line lacks a SKU or quantity, so none does."""

    model_config = ConfigDict(from_attributes=True)

    position: int
    customer_text: str
    sku: str
    quantity: int  # individual items
    unit_cents: int
    line_cents: int
    discount_cents: int
    total_cents: int


class ExportedChange(BaseModel):
    """One review action: a line correction, or the sign-off (`field` "status", no line)."""

    at: datetime
    line: int | None
    field: str
    old_value: str | None
    new_value: str | None
    status_before: DraftStatus
    status_after: DraftStatus


class ExportedOrder(BaseModel):
    order_ref: str
    source_request: str  # the request that created the draft
    later_requests: list[str]  # duplicates and conflicts with the same order_ref
    reviewed_at: datetime
    lines: list[ExportedLine]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    findings: list[Finding]  # review findings the reviewer signed off, e.g. a conflicting request
    history: list[ExportedChange]


class ReviewedExport(BaseModel):
    exported_at: datetime
    currency: Literal["USD"] = "USD"
    orders: list[ExportedOrder]
