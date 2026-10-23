from typing import Any, Protocol

from pydantic import BaseModel

from app.core.enums import ResponseSource


class ModelResponse(BaseModel):
    """One model reply, labelled so reviewers can tell real calls from replays."""

    source: ResponseSource
    model: str
    content: Any
    raw: dict[str, Any]


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        cache_key: str,
    ) -> ModelResponse: ...
