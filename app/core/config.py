from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    debug: bool = False
    database_url: str = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'var' / 'orders.db').as_posix()}"

    seed_dir: Path = PROJECT_ROOT / "data" / "seed"
    inbox_dir: Path = PROJECT_ROOT / "data" / "inbox"
    replay_dir: Path = PROJECT_ROOT / "replays"

    # live: call the provider and save each response; replay: serve saved responses, no key needed
    model_mode: Literal["live", "replay"] = "replay"
    model_name: str = ""
    model_temperature: float = 0.0
    model_max_tokens: int = 1024
    model_timeout_s: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
