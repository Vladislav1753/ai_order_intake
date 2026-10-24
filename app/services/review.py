"""Reviewer actions: correct a draft line and re-run the checks, or sign a draft off."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DraftStatus, FindingCode
from app.core.errors import InvalidDataError, NotFoundError
from app.db.errors import translate_db_errors
from app.models import Correction, DraftLine, DraftOrder
from app.repositories.drafts import DraftRepository
from app.repositories.products import ProductRepository
from app.schemas.draft import Finding, LineInput
from app.schemas.review import CorrectionField, LineCorrection
from app.services.clarification import clarification_text
from app.services.validation import CLARIFICATION_CODES, check_lines
from app.utils.time import utcnow


class ReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.drafts = DraftRepository(session)
        self.products = ProductRepository(session)

    async def correct(self, draft_id: int, change: LineCorrection) -> DraftOrder:
        """Apply one field change, then re-run validation, pricing and status (no model call).

        Saves a `corrections` row with the old and new value and the status change. Setting
        the value a line already has saves nothing.
        """
        draft = await self._get(draft_id)
        line = next((line for line in draft.lines if line.position == change.line), None)
        if line is None:
            raise NotFoundError(f"Draft {draft_id} has no line {change.line}")
        catalog = {product.sku: product.unit_cents for product in await self.products.list_all()}
        new = change.new_value
        if change.field is CorrectionField.SKU and new is not None and new not in catalog:
            raise InvalidDataError(f"{new} is not in the catalog")
        old = getattr(line, change.field.value)
        if old == new:
            return draft

        status_before = draft.status
        kept = _kept_findings(draft, change)
        setattr(line, change.field.value, new)
        _revalidate(draft, catalog, kept)
        draft.corrections.append(
            Correction(
                draft_line_id=line.id,
                field=change.field.value,
                old_value=_text(old),
                new_value=_text(new),
                status_before=status_before,
                status_after=draft.status,
            )
        )
        await self._commit()
        return draft

    async def mark_reviewed(self, draft_id: int) -> DraftOrder:
        """The explicit sign-off: the only way a draft becomes `reviewed`.

        A draft with open customer questions can't be signed off. Remaining review findings
        (a conflicting request, an unverified SKU) are what the reviewer acknowledges here.
        """
        draft = await self._get(draft_id)
        if draft.status == DraftStatus.REVIEWED:
            return draft
        if draft.status == DraftStatus.NEEDS_CLARIFICATION:
            raise InvalidDataError(
                "This draft still needs clarification: every line needs a catalog SKU and a "
                "quantity of individual items before it can be marked reviewed."
            )
        status_before = draft.status
        draft.status = DraftStatus.REVIEWED
        draft.reviewed_at = utcnow()
        draft.corrections.append(
            Correction(
                field="status",
                old_value=status_before.value,
                new_value=draft.status.value,
                status_before=status_before,
                status_after=draft.status,
            )
        )
        await self._commit()
        return draft

    async def _get(self, draft_id: int) -> DraftOrder:
        draft = await self.drafts.get(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found")
        return draft

    async def _commit(self) -> None:
        with translate_db_errors():
            await self.session.commit()


def _kept_findings(draft: DraftOrder, change: LineCorrection) -> list[Finding]:
    """Findings the line checks can't re-derive, so they carry over.

    A conflicting request stays; marking the draft reviewed acknowledges it. An unverified
    SKU stays until the reviewer sets that line's SKU.
    """
    findings = [Finding.model_validate(finding) for finding in draft.findings]
    return [
        finding
        for finding in findings
        if finding.code not in CLARIFICATION_CODES
        and not (
            finding.code == FindingCode.UNVERIFIED_SKU
            and change.field is CorrectionField.SKU
            and finding.line == change.line
        )
    ]


def _revalidate(draft: DraftOrder, catalog: Mapping[str, int], kept: Sequence[Finding]) -> None:
    proposed = draft.proposal_json["lines"]
    checked = check_lines([_line_input(line, proposed) for line in draft.lines], catalog, kept)
    for line, result in zip(draft.lines, checked.lines, strict=True):
        line.unit_cents = result.unit_cents
        line.line_cents = result.line_cents
        line.discount_cents = result.discount_cents
        line.total_cents = result.total_cents
    draft.status = checked.status
    draft.subtotal_cents = checked.subtotal_cents
    draft.discount_cents = checked.discount_cents
    draft.total_cents = checked.total_cents
    draft.findings = [finding.model_dump(mode="json") for finding in checked.findings]
    draft.clarification_text = clarification_text(draft.order_ref, checked)
    draft.reviewed_at = None


def _line_input(line: DraftLine, proposed: Sequence[Mapping[str, Any]]) -> LineInput:
    """The line's current values. The model's tied matches still apply while the SKU is open,
    so clearing a SKU the model left ambiguous makes it ambiguous again, not unknown."""
    proposal = LineInput.model_validate(proposed[line.position - 1])
    return LineInput(
        customer_text=line.customer_text,
        matched_query=proposal.matched_query,
        sku=line.sku,
        quantity=line.quantity,
        unit_label=line.unit_label,
        candidates=proposal.candidates if proposal.sku is None else [],
    )


def _text(value: str | int | None) -> str | None:
    return None if value is None else str(value)
