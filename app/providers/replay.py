import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.core.enums import ResponseSource
from app.providers.base import LLMProvider, ModelResponse, ProviderError
from app.utils.time import utcnow

SIMULATED_FAILURES_FILE = "simulated-failures.json"


class ReplayStore:
    """One JSON file per model call in `replays/`, named by its cache key."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    async def save(self, cache_key: str, request: dict[str, Any], response: dict[str, Any]) -> None:
        record = {
            "cache_key": cache_key,
            "recorded_at": utcnow().isoformat(),
            "request": request,
            "response": response,
        }
        await asyncio.to_thread(self._write, self._path(cache_key), record)

    async def load(self, cache_key: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._read, self._path(cache_key))

    def _path(self, cache_key: str) -> Path:
        return self.directory / f"{cache_key}.json"

    @staticmethod
    def _write(path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")  # same bytes on every OS

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data


class ReplayProvider:
    """Serves saved real responses, labelled `cached`. Needs no API key or network."""

    def __init__(self, directory: Path) -> None:
        self._store = ReplayStore(directory)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
        response_format: dict[str, Any],
        cache_key: str,
    ) -> ModelResponse:
        record = await self._store.load(cache_key)
        if record is None:
            raise ProviderError(
                f"no saved response {cache_key}.json; record it with MODEL_MODE=live",
                source=ResponseSource.CACHED,
            )
        raw = record["response"]
        return ModelResponse(
            source=ResponseSource.CACHED,
            model=raw["model"],
            message=raw["choices"][0]["message"],
            raw=raw,
        )


class SimulatedFailures:
    """Fails the listed request ids on purpose, labelled `simulated-failure`, in any mode."""

    def __init__(self, inner: LLMProvider, failures: Mapping[str, str]) -> None:
        self._inner = inner
        self._failures = failures

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str,
        response_format: dict[str, Any],
        cache_key: str,
    ) -> ModelResponse:
        request_id = cache_key.split(".", 1)[0]
        if request_id in self._failures:
            raise ProviderError(self._failures[request_id], source=ResponseSource.SIMULATED_FAILURE)
        return await self._inner.complete(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            cache_key=cache_key,
        )


def load_simulated_failures(directory: Path) -> dict[str, str]:
    """`replays/simulated-failures.json`: request id -> error message."""
    path = directory / SIMULATED_FAILURES_FILE
    if not path.exists():
        return {}
    failures: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return failures
