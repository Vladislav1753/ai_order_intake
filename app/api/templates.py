"""The Jinja2 environment for app/templates, with the display helpers the pages share."""

from datetime import datetime
from pathlib import Path

from fastapi.templating import Jinja2Templates

STATUS_LABELS = {
    "failed": "Failed",
    "needs_clarification": "Needs clarification",
    "needs_review": "Needs review",
    "ready_for_review": "Ready for review",
    "reviewed": "Reviewed",
    "pending": "Pending",
    "drafted": "Drafted",
    "duplicate": "Duplicate",
    "conflict": "Conflict",
}
REASON_LABELS = {
    "unknown_product": "Unknown product",
    "ambiguous_product": "Ambiguous product",
    "ambiguous_quantity": "Ambiguous quantity",
    "non_individual_unit": "Box or pack quantity",
    "unverified_sku": "SKU not backed by a search",
    "conflicting_request": "Conflicting request",
    "unusable_input": "Unusable input file",
    "model_failure": "Model call failed",
}


def money(cents: int | None) -> str:
    """Integer cents as dollars, without going through float."""
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"


def when(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M UTC") if moment else "—"


templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
templates.env.filters.update(money=money, when=when)
templates.env.globals.update(STATUS_LABELS=STATUS_LABELS, REASON_LABELS=REASON_LABELS)
