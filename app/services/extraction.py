"""The model step: a bounded tool loop where the only tool is the local catalog search."""

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.core.errors import DomainError
from app.models import Product
from app.providers.base import LLMProvider, ProviderError
from app.providers.prompts import EXTRACT_SYSTEM, PROMPT_VERSION
from app.providers.schema import function_tool, json_schema_format
from app.schemas.extraction import CatalogHit, CatalogSearch, ExtractionResult, SearchCatalogArgs
from app.services.catalog import search_catalog

SEARCH_TOOL = function_tool(
    SearchCatalogArgs,
    name="search_catalog",
    description=(
        "Search the product catalog by SKU or product words. Returns the best matches "
        "(sku, name); several results mean the words fit more than one product."
    ),
)
RESULT_FORMAT = json_schema_format(ExtractionResult, name="extraction_result")


class ExtractionError(DomainError):
    """No usable model output. `calls` keeps every round trip made before the failure."""

    def __init__(self, message: str, calls: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.calls = calls


@dataclass(frozen=True)
class Extraction:
    result: ExtractionResult
    searches: list[CatalogSearch]
    calls: list[dict[str, Any]]


def describe_catalog(product_count: int) -> str:
    """The catalog part of the prompt, built from the `Product` model, never from its rows."""
    columns = [column for column in Product.__table__.columns if "search" in column.info]
    lines = [
        f"Table `{Product.__tablename__}` has {product_count} products. `search_catalog` "
        "matches your query against these fields and returns them:"
    ]
    lines += [f"- `{column.name}`: {column.info['search']}" for column in columns]
    return "\n".join(lines)


def render_system_prompt(product_count: int, search_budget: int) -> str:
    return EXTRACT_SYSTEM.format(
        catalog=describe_catalog(product_count), search_budget=search_budget
    )


async def extract_order(
    *,
    request_id: str,
    text: str,
    products: Sequence[Product],
    provider: LLMProvider,
    search_budget: int,
) -> Extraction:
    """Ask the model for order lines, answering its catalog searches until it gives a result.

    Each step may search while budget is left; after that `tool_choice="none"` forces the
    final answer. Raises `ExtractionError` on provider failure or invalid output.
    """
    system = render_system_prompt(len(products), search_budget)
    prompt_hash = hashlib.sha256(system.encode()).hexdigest()[:12]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]
    searches: list[CatalogSearch] = []
    calls: list[dict[str, Any]] = []
    search_calls = 0
    for step in range(1, search_budget + 2):
        tool_choice = "auto" if search_calls < search_budget else "none"
        cache_key = _cache_key(request_id, step, messages, tool_choice)
        call: dict[str, Any] = {
            "step": step,
            "cache_key": cache_key,
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": prompt_hash,
            "tool_choice": tool_choice,
        }
        calls.append(call)
        try:
            response = await provider.complete(
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice=tool_choice,
                response_format=RESULT_FORMAT,
                cache_key=cache_key,
            )
        except ProviderError as exc:
            call.update(source=exc.source, error=str(exc))
            raise ExtractionError(str(exc), calls) from exc
        message = response.message
        call.update(source=response.source, model=response.model, response=message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return Extraction(_parse_result(message, calls), searches, calls)
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": [_clean_tool_call(tool_call) for tool_call in tool_calls],
            }
        )
        call["tool_results"] = []
        for tool_call in tool_calls:
            search_calls += 1
            content = _run_tool(tool_call, products, searches, search_calls <= search_budget)
            call["tool_results"].append(content)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call["id"], "content": json.dumps(content)}
            )
    raise ExtractionError("no final answer within the step budget", calls)


def _run_tool(
    tool_call: dict[str, Any],
    products: Sequence[Product],
    searches: list[CatalogSearch],
    within_budget: bool,
) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    if function.get("name") != SEARCH_TOOL["function"]["name"]:
        return {"error": f"unknown tool {function.get('name')!r}"}
    if not within_budget:
        return {"error": "search budget used up; answer with what you found"}
    try:
        args = SearchCatalogArgs.model_validate_json(function.get("arguments") or "")
    except ValidationError as exc:
        return {"error": f"invalid arguments: {exc.errors()[0]['msg']}"}
    hits = [CatalogHit(sku=p.sku, name=p.name) for p in search_catalog(products, args.query)]
    searches.append(CatalogSearch(query=args.query, results=hits))
    if not hits:
        return {"results": [], "hint": "No match. Try other words, the SKU, or fewer words."}
    return {"results": [hit.model_dump() for hit in hits]}


def _parse_result(message: dict[str, Any], calls: list[dict[str, Any]]) -> ExtractionResult:
    if message.get("refusal"):
        raise ExtractionError(f"model refused: {message['refusal']}", calls)
    try:
        return ExtractionResult.model_validate_json(message.get("content") or "")
    except ValidationError as exc:
        raise ExtractionError(f"invalid model output: {exc.error_count()} errors", calls) from exc


def _clean_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function") or {}
    return {
        "id": tool_call["id"],
        "type": "function",
        "function": {"name": function.get("name"), "arguments": function.get("arguments")},
    }


def _cache_key(request_id: str, step: int, messages: list[dict[str, Any]], tool_choice: str) -> str:
    """`<request id>.<step>.<digest>`: a prompt, schema, or conversation change is a new key."""
    payload = {
        "messages": messages,
        "tools": [SEARCH_TOOL],
        "tool_choice": tool_choice,
        "response_format": RESULT_FORMAT,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    return f"{re.sub(r'[^A-Za-z0-9_-]', '_', request_id)}.{step:02d}.{digest}"
