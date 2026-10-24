import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.core.enums import ResponseSource
from app.providers.base import ProviderError
from app.providers.openai_chat import OpenAIChatProvider
from app.providers.replay import ReplayProvider, SimulatedFailures

CALL: dict[str, Any] = {
    "messages": [{"role": "user", "content": "2 CAB-1"}],
    "tools": [],
    "tool_choice": "auto",
    "response_format": {},
}
COMPLETION = {
    "model": "gpt-test",
    "choices": [{"message": {"role": "assistant", "content": "{}", "tool_calls": None}}],
}


class FakeCompletions:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def create(self, **request: Any) -> SimpleNamespace:
        if self.error:
            raise self.error
        return SimpleNamespace(model_dump=lambda mode: COMPLETION)


def live(tmp_path: Path, completions: FakeCompletions) -> OpenAIChatProvider:
    settings = Settings(_env_file=None, model_api_key="test-key", replay_dir=tmp_path)  # type: ignore[call-arg]
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return OpenAIChatProvider(settings, client=client)


async def test_live_response_is_saved_and_replays_as_cached(tmp_path: Path) -> None:
    response = await live(tmp_path, FakeCompletions()).complete(**CALL, cache_key="R1.01.abc")
    replayed = await ReplayProvider(tmp_path).complete(**CALL, cache_key="R1.01.abc")

    assert response.source is ResponseSource.LIVE
    assert replayed.source is ResponseSource.CACHED
    assert replayed.message == response.message
    saved = json.loads((tmp_path / "R1.01.abc.json").read_text(encoding="utf-8"))
    assert saved["request"]["model"] == "gpt-4.1-mini"
    assert "test-key" not in json.dumps(saved)


async def test_timeout_is_a_provider_error(tmp_path: Path) -> None:
    provider = live(tmp_path, FakeCompletions(TimeoutError()))

    with pytest.raises(ProviderError, match="model unavailable"):
        await provider.complete(**CALL, cache_key="R1.01.x")


async def test_missing_replay_is_a_provider_error(tmp_path: Path) -> None:
    with pytest.raises(ProviderError, match="no saved response"):
        await ReplayProvider(tmp_path).complete(**CALL, cache_key="R1.01.missing")


async def test_simulated_failure_is_labelled(tmp_path: Path) -> None:
    provider = SimulatedFailures(ReplayProvider(tmp_path), {"R9": "simulated outage"})

    with pytest.raises(ProviderError) as caught:
        await provider.complete(**CALL, cache_key="R9.01.abc")

    assert caught.value.source is ResponseSource.SIMULATED_FAILURE
