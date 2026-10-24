from typing import Any, Protocol

from pydantic import BaseModel

from app.core.enums import ResponseSource


class ModelResponse(BaseModel):
    """One model reply, labelled so reviewers can tell real calls from replays."""

    source: ResponseSource
    model: str
    message: dict[str, Any]  # the assistant message: content and/or tool_calls
    raw: dict[str, Any]


class ProviderError(Exception):
    """The model could not answer: API error, timeout, missing replay, or a simulated failure."""

    def __init__(self, message: str, source: ResponseSource = ResponseSource.LIVE) -> None:
        super().__init__(message)
        self.source = source


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
        response_format: dict[str, Any],
        cache_key: str,
    ) -> ModelResponse:
        """`cache_key` is `<request id>.<step>.<digest of the call>`, unique per call."""
        ...
