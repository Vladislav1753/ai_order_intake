"""Read side of the review screens: queue counts, the filtered queue, and one draft's evidence."""

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DraftStatus, RequestStatus
from app.core.errors import NotFoundError
from app.models import DraftLine, DraftOrder, IncomingRequest, Product
from app.repositories.drafts import DraftRepository
from app.repositories.products import ProductRepository
from app.repositories.requests import RequestRepository
from app.schemas.draft import Finding

QueueFilter = Literal[
    "failed", "needs_clarification", "needs_review", "ready_for_review", "reviewed"
]
QUEUE_FILTERS: tuple[QueueFilter, ...] = (
    "failed",
    "needs_clarification",
    "needs_review",
    "ready_for_review",
    "reviewed",
)
UNUSABLE_INPUT = "unusable_input"
MODEL_FAILURE = "model_failure"


@dataclass(frozen=True)
class QueueItem:
    """One row: a draft order, or a request that failed before it became one."""

    kind: Literal["draft", "request"]
    id: int
    order_ref: str
    status: str
    summary: str
    reasons: list[str]
    total_cents: int | None
    updated_at: datetime


@dataclass(frozen=True)
class QueueSummary:
    requests: int
    new_orders: int
    counts: dict[str, int]  # per queue filter
    reasons: list[tuple[str, int]]  # open exception reasons, most common first
    duplicates: list[IncomingRequest]
    conflicts: list[IncomingRequest]


@dataclass(frozen=True)
class LineView:
    line: DraftLine
    proposed: dict[str, Any]  # the resolved model proposal for this line
    changed: frozenset[str]  # fields the reviewer changed from the proposal
    findings: list[Finding]


@dataclass(frozen=True)
class DraftDetail:
    draft: DraftOrder
    source: IncomingRequest
    others: list[IncomingRequest]  # later requests with the same order_ref
    lines: list[LineView]
    order_findings: list[Finding]  # findings about the whole draft
    products: list[Product]
    call_sources: dict[str, int]


@dataclass(frozen=True)
class CallView:
    """One saved model round trip, labelled by where the response came from."""

    step: int
    source: str  # live | cached | simulated-failure
    model: str | None
    prompt_version: str | None
    outcome: str


@dataclass(frozen=True)
class RequestDetail:
    request: IncomingRequest
    draft: DraftOrder | None
    calls: list[CallView]
    reason: str | None  # why it failed, as a queue reason code


class QueueService:
    def __init__(self, session: AsyncSession) -> None:
        self.requests = RequestRepository(session)
        self.drafts = DraftRepository(session)
        self.products = ProductRepository(session)

    async def summary(self) -> QueueSummary:
        """Duplicates and conflicts are counted apart: they never create a new order."""
        requests = await self.requests.list_all()
        drafts = await self.drafts.list_all()
        failed = [r for r in requests if r.status is RequestStatus.FAILED]
        counts = Counter[str](draft.status.value for draft in drafts)
        counts[RequestStatus.FAILED.value] = len(failed)
        reasons = Counter[str]()
        for draft in drafts:
            if draft.status is not DraftStatus.REVIEWED:
                reasons.update({finding["code"] for finding in draft.findings})
        reasons.update(failure_reason(request) for request in failed)
        return QueueSummary(
            requests=len(requests),
            new_orders=len(drafts),
            counts={name: counts[name] for name in QUEUE_FILTERS},
            reasons=reasons.most_common(),
            duplicates=[r for r in requests if r.status is RequestStatus.DUPLICATE],
            conflicts=[r for r in requests if r.status is RequestStatus.CONFLICT],
        )

    async def items(self, status: QueueFilter | None = None) -> list[QueueItem]:
        """Failures first, then what blocks an order, then what a person still has to see."""
        items = []
        if status is None or status == RequestStatus.FAILED.value:
            items += [_request_item(r) for r in await self.requests.list_all(RequestStatus.FAILED)]
        if status != RequestStatus.FAILED.value:
            wanted = DraftStatus(status) if status else None
            items += [_draft_item(draft) for draft in await self.drafts.list_all(wanted)]
        order: dict[str, int] = {name: rank for rank, name in enumerate(QUEUE_FILTERS)}
        return sorted(items, key=lambda item: order[item.status])

    async def draft_detail(self, draft_id: int) -> DraftDetail:
        draft = await self.drafts.get(draft_id)
        if draft is None:
            raise NotFoundError(f"Draft {draft_id} not found")
        requests = await self.requests.list_by_order_ref(draft.order_ref)
        source = next(r for r in requests if r.id == draft.source_request_id)
        findings = [Finding.model_validate(finding) for finding in draft.findings]
        proposed = draft.proposal_json["lines"]
        lines = []
        for line in draft.lines:
            proposal = proposed[line.position - 1]
            lines.append(
                LineView(
                    line=line,
                    proposed=proposal,
                    changed=frozenset(
                        name
                        for name in ("sku", "quantity")
                        if getattr(line, name) != proposal[name]
                    ),
                    findings=[finding for finding in findings if finding.line == line.position],
                )
            )
        return DraftDetail(
            draft=draft,
            source=source,
            others=[r for r in requests if r.id != source.id],
            lines=lines,
            order_findings=[finding for finding in findings if finding.line is None],
            products=await self.products.list_all(),
            call_sources=dict(Counter(str(call.get("source")) for call in source.model_calls)),
        )

    async def request_detail(self, request_id: int) -> RequestDetail:
        request = await self.requests.get(request_id)
        if request is None:
            raise NotFoundError(f"Request {request_id} not found")
        draft = await self.drafts.get_by_order_ref(request.order_ref) if request.order_ref else None
        return RequestDetail(
            request=request,
            draft=draft,
            calls=[_call_view(call) for call in request.model_calls],
            reason=failure_reason(request) if request.status is RequestStatus.FAILED else None,
        )


def failure_reason(request: IncomingRequest) -> str:
    error = request.error or ""
    return UNUSABLE_INPUT if error.startswith("Unusable input") else MODEL_FAILURE


def _draft_item(draft: DraftOrder) -> QueueItem:
    summary = (
        ", ".join(f"{line.quantity or '?'} x {line.sku or '?'}" for line in draft.lines)
        or "no lines"
    )
    return QueueItem(
        kind="draft",
        id=draft.id,
        order_ref=draft.order_ref,
        status=draft.status.value,
        summary=summary,
        reasons=list(dict.fromkeys(finding["code"] for finding in draft.findings)),
        total_cents=draft.total_cents,
        updated_at=draft.updated_at,
    )


def _request_item(request: IncomingRequest) -> QueueItem:
    return QueueItem(
        kind="request",
        id=request.id,
        order_ref=request.order_ref,
        status=request.status.value,
        summary=Path(request.source_path).name if request.source_path else request.external_id,
        reasons=[failure_reason(request)],
        total_cents=None,
        updated_at=request.processed_at or request.created_at,
    )


def _call_view(call: dict[str, Any]) -> CallView:
    if call.get("error"):
        outcome = f"Error: {call['error']}"
    elif tool_calls := (call.get("response") or {}).get("tool_calls"):
        searches = []
        for tool_call, result in zip(tool_calls, call.get("tool_results", []), strict=False):
            found = ", ".join(hit["sku"] for hit in result.get("results", []))
            query = _query(tool_call["function"]["arguments"])
            searches.append(f"{query!r} -> {found or result.get('error') or 'nothing'}")
        outcome = "Searched " + "; ".join(searches)
    else:
        outcome = "Final answer"
    return CallView(
        step=call["step"],
        source=str(call.get("source")),
        model=call.get("model"),
        prompt_version=call.get("prompt_version"),
        outcome=outcome,
    )


def _query(arguments: str) -> str:
    try:
        return str(json.loads(arguments)["query"])
    except (ValueError, KeyError, TypeError):
        return arguments
