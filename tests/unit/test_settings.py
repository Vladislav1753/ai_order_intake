import pytest

from app.core.config import PROJECT_ROOT, Settings


def test_empty_env_value_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: `DATABASE_URL=` copied from .env.example used to override the default with "".
    monkeypatch.setenv("DATABASE_URL", "")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert (
        settings.database_url
        == f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'var' / 'orders.db').as_posix()}"
    )
