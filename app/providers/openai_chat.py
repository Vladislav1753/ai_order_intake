import asyncio
from typing import Any

from openai import AsyncOpenAI, OpenAIError

from app.core.config import Settings
from app.core.enums import ResponseSource
from app.providers.base import ModelResponse, ProviderError
from app.providers.replay import ReplayStore


class OpenAIChatProvider:
    """Live Chat Completions calls. Every response is saved to `replays/` for key-free reruns."""

    def __init__(self, settings: Settings, client: Any = None) -> None:
        if settings.model_api_key is None:
            raise ValueError("MODEL_API_KEY is required when MODEL_MODE=live")
        self._settings = settings
        # Typed as Any: the SDK's TypedDict params don't accept the plain dicts used here.
        self._client: Any = client or AsyncOpenAI(
            api_key=settings.model_api_key.get_secret_value(),
            timeout=settings.model_timeout_s,
            max_retries=1,
        )
        self._replays = ReplayStore(settings.replay_dir)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
        response_format: dict[str, Any],
        cache_key: str,
    ) -> ModelResponse:
        request = {
            "model": self._settings.model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "response_format": response_format,
            "temperature": self._settings.model_temperature,
            "max_completion_tokens": self._settings.model_max_tokens,
        }
        try:
            async with asyncio.timeout(self._settings.model_timeout_s):
                completion = await self._client.chat.completions.create(**request)
        except (OpenAIError, TimeoutError) as exc:
            raise ProviderError(f"model unavailable: {type(exc).__name__}: {exc}") from exc
        raw: dict[str, Any] = completion.model_dump(mode="json")
        if not raw.get("choices"):
            raise ProviderError("model returned no choices")
        await self._replays.save(cache_key, request, raw)
        return ModelResponse(
            source=ResponseSource.LIVE,
            model=raw["model"],
            message=raw["choices"][0]["message"],
            raw=raw,
        )
