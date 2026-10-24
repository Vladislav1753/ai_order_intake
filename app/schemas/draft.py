"""Validation input and output. `Finding` is also the shape of `draft_orders.findings` rows."""

from pydantic import BaseModel

from app.core.enums import DraftStatus, FindingCode
from app.schemas.extraction import CatalogHit


class Finding(BaseModel):
    code: FindingCode
    line: int | None  # 1-based line position; None for the whole draft
    message: str


class LineInput(BaseModel):
    """One line before checks, as resolved from the model output or corrected by a reviewer.

    `candidates` are the catalog entries that support the line: the single match when `sku`
    is set, the tied matches when the product is ambiguous. `matched_query` is the search the
    model cited for the line.
    """

    customer_text: str
    matched_query: str | None = None
    sku: str | None
    quantity: int | None  # individual items
    unit_label: str | None
    candidates: list[CatalogHit] = []


class CheckedLine(LineInput):
    position: int
    unit_cents: int | None = None
    line_cents: int | None = None
    discount_cents: int | None = None
    total_cents: int | None = None


class CheckedDraft(BaseModel):
    lines: list[CheckedLine]
    findings: list[Finding]
    status: DraftStatus
    subtotal_cents: int
    discount_cents: int
    total_cents: int
