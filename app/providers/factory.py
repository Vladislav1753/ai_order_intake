from app.core.config import Settings
from app.providers.base import LLMProvider
from app.providers.openai_chat import OpenAIChatProvider
from app.providers.replay import ReplayProvider, SimulatedFailures, load_simulated_failures


def make_provider(settings: Settings) -> LLMProvider:
    """`MODEL_MODE=live` calls the API and records; `replay` serves the recordings."""
    inner: LLMProvider
    if settings.model_mode == "live":
        inner = OpenAIChatProvider(settings)
    else:
        inner = ReplayProvider(settings.replay_dir)
    return SimulatedFailures(inner, load_simulated_failures(settings.replay_dir))
