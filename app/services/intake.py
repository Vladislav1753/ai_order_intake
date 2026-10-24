"""Processing one request: ingest, dedupe, extract, validate and price, save."""

import hashlib
import logging
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.enums import DraftStatus, FindingCode, RequestStatus
from app.db.errors import translate_db_errors
from app.models import DraftLine, DraftOrder, IncomingRequest
from app.providers.base import LLMProvider
from app.providers.prompts import PROMPT_VERSION
from app.repositories.drafts import DraftRepository
from app.repositories.products import ProductRepository
from app.repositories.requests import RequestRepository
from app.schemas.draft import Finding
from app.schemas.seed import RequestIn
from app.services.clarification import clarification_text
from app.services.extraction import ExtractionError, extract_order
from app.services.validation import check_lines, resolve_model_lines, status_for
from app.utils.time import utcnow

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntakeResult:
    external_id: str
    order_ref: str
    status: RequestStatus
    draft_status: DraftStatus | None = None
    error: str | None = None
    # True when an earlier run already processed this request: nothing was done this time,
    # so it must not be counted as a new draft (or a new duplicate) again.
    already_processed: bool = False


def content_hash(text: str) -> str:
    """Ignores whitespace, so a re-sent email with other line breaks is still a duplicate."""
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


class IntakeService:
    def __init__(self, session: AsyncSession, provider: LLMProvider, settings: Settings) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings
        self.requests = RequestRepository(session)
        self.drafts = DraftRepository(session)
        self.products = ProductRepository(session)

    async def process(self, item: RequestIn, source_path: str | None = None) -> IntakeResult:
        """Idempotent: a request already processed (other than failed) is left as it is.

        Model failures become a `failed` request. Database failures raise `DomainError`; the
        request then stays `pending` and is retried on the next run.
        """
        request = await self.requests.get_by_external_id(item.id)
        if request is not None and request.status not in (
            RequestStatus.PENDING,
            RequestStatus.FAILED,
        ):
            draft = await self.drafts.get_by_order_ref(request.order_ref)
            return replace(self._result(request, draft), already_processed=True)
        if request is None:
            request = IncomingRequest(
                external_id=item.id,
                order_ref=item.order_ref,
                text=item.text,
                source_path=source_path,
                content_hash=content_hash(item.text),
            )
            self.requests.add(request)
        # Commit the raw request first: it survives a crash, and no write lock is held while
        # the model call runs.
        await self._commit()

        draft = await self.drafts.get_by_order_ref(request.order_ref)
        if draft is not None:
            return await self._same_order(request, draft)
        return await self._new_draft(request)

    async def record_unusable(
        self, *, external_id: str, source_path: str, raw_text: str, error: str
    ) -> IntakeResult:
        """Keep a file that couldn't be read as a `failed` request, so the queue shows it."""
        request = await self.requests.get_by_external_id(external_id)
        if request is None:
            request = IncomingRequest(
                external_id=external_id,
                order_ref="",
                text=raw_text,
                source_path=source_path,
                content_hash=content_hash(raw_text),
            )
            self.requests.add(request)
        request.status = RequestStatus.FAILED
        request.error = f"Unusable input: {error}"
        request.processed_at = utcnow()
        await self._commit()
        return self._result(request, None)

    async def _same_order(self, request: IncomingRequest, draft: DraftOrder) -> IntakeResult:
        """A second request for an order never creates a draft. Different text is a conflict."""
        source = await self.requests.get(draft.source_request_id)
        if source is not None and source.content_hash == request.content_hash:
            request.status = RequestStatus.DUPLICATE
        else:
            request.status = RequestStatus.CONFLICT
            findings = [Finding.model_validate(finding) for finding in draft.findings]
            findings.append(
                Finding(
                    code=FindingCode.CONFLICTING_REQUEST,
                    line=None,
                    message=(
                        f"Request {request.external_id} has this order reference but different "
                        "text. Check whether it changes the order."
                    ),
                )
            )
            draft.findings = [finding.model_dump(mode="json") for finding in findings]
            draft.status = status_for(findings)
        request.error = None
        request.processed_at = utcnow()
        await self._commit()
        return self._result(request, draft)

    async def _new_draft(self, request: IncomingRequest) -> IntakeResult:
        products = await self.products.list_all()
        try:
            extraction = await extract_order(
                request_id=request.external_id,
                text=request.text,
                products=products,
                provider=self.provider,
                search_budget=self.settings.catalog_search_budget,
            )
        except ExtractionError as exc:
            log.warning("request %s failed: %s", request.external_id, exc)
            request.status = RequestStatus.FAILED
            request.error = str(exc)
            request.model_calls = exc.calls
            request.processed_at = utcnow()
            await self._commit()
            return self._result(request, None)

        lines, model_findings = resolve_model_lines(extraction.result.lines, extraction.searches)
        catalog = {product.sku: product.unit_cents for product in products}
        checked = check_lines(lines, catalog, extra=model_findings)
        draft = DraftOrder(
            order_ref=request.order_ref,
            source_request_id=request.id,
            status=checked.status,
            subtotal_cents=checked.subtotal_cents,
            discount_cents=checked.discount_cents,
            total_cents=checked.total_cents,
            proposal_json={
                "prompt_version": PROMPT_VERSION,
                "model": extraction.calls[-1].get("model"),
                "result": extraction.result.model_dump(mode="json"),
                "searches": [search.model_dump(mode="json") for search in extraction.searches],
                "lines": [line.model_dump(mode="json") for line in lines],
            },
            findings=[finding.model_dump(mode="json") for finding in checked.findings],
            clarification_text=clarification_text(request.order_ref, checked),
            lines=[
                DraftLine(**line.model_dump(exclude={"candidates", "matched_query"}))
                for line in checked.lines
            ],
        )
        self.drafts.add(draft)
        request.status = RequestStatus.DRAFTED
        request.error = None
        request.model_calls = extraction.calls
        request.processed_at = utcnow()
        await self._commit()
        return self._result(request, draft)

    async def _commit(self) -> None:
        with translate_db_errors():
            await self.session.commit()

    @staticmethod
    def _result(request: IncomingRequest, draft: DraftOrder | None) -> IntakeResult:
        return IntakeResult(
            external_id=request.external_id,
            order_ref=request.order_ref,
            status=request.status,
            draft_status=draft.status if draft else None,
            error=request.error,
        )
