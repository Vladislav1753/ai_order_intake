"""A scripted stand-in for the model, and builders for the messages it would send."""

import json
from typing import Any

from app.core.enums import ResponseSource
from app.providers.base import ModelResponse, ProviderError


class ScriptedProvider:
    """Replies with canned assistant messages per request id, in order. Never networked."""

    def __init__(self, scripts: dict[str, list[dict[str, Any]]]) -> None:
        self._scripts = {request_id: list(replies) for request_id, replies in scripts.items()}
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
        response_format: dict[str, Any],
        cache_key: str,
    ) -> ModelResponse:
        self.calls.append({"cache_key": cache_key, "tool_choice": tool_choice})
        replies = self._scripts.get(cache_key.split(".", 1)[0])
        if not replies:
            raise ProviderError("no scripted reply", source=ResponseSource.CACHED)
        return ModelResponse(
            source=ResponseSource.CACHED, model="scripted", message=replies.pop(0), raw={}
        )


def search(*queries: str) -> dict[str, Any]:
    """An assistant turn calling `search_catalog` once per query."""
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{number}",
                "type": "function",
                "function": {"name": "search_catalog", "arguments": json.dumps({"query": query})},
            }
            for number, query in enumerate(queries, start=1)
        ],
    }


def answer(*lines: dict[str, Any]) -> dict[str, Any]:
    return {"role": "assistant", "content": json.dumps({"lines": list(lines)}), "tool_calls": None}


def item(
    text: str,
    sku: str | None,
    quantity: int | None,
    unit: str | None = "item",
    candidates: tuple[str, ...] = (),
    query: str | None = None,
) -> dict[str, Any]:
    """One answer line. `query` is the search the model cites for `sku` (defaults to the SKU)."""
    return {
        "customer_text": text,
        "matched_query": query or sku,
        "sku": sku,
        "candidate_skus": list(candidates),
        "quantity": quantity,
        "unit": unit,
    }


# Plausible model behaviour for the four seed requests (data/seed/seed.json).
SEED_SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "R1": [search("CAB-1"), answer(item("2 individual CAB-1 cables", "CAB-1", 2))],
    "R2": [
        search("Moon adapter"),
        search("adapter"),
        answer(item("one Moon adapter", None, 1)),
    ],
    "R3": [
        search("usual cable"),
        answer(item("two boxes of the usual cable", None, 2, "box", candidates=("CAB-1", "CAB-2"))),
    ],
    "R4": [search("CAB-1"), answer(item("2 individual CAB-1 cables", "CAB-1", 2))],
}
