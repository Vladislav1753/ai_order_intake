"""Smoke test of the real entry point: `seed` then `process` in replay mode on a fresh DB.

Sync tests on purpose: `main()` runs its own event loop with `asyncio.run`.
"""

import asyncio
from pathlib import Path

import pytest

from app.cli import main
from app.core.config import Settings
from app.db.migrations import run_alembic
from app.db.session import make_engine


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'cli.db').as_posix()}"

    async def migrate() -> None:
        engine = make_engine(url)
        await run_alembic(engine, "upgrade", "head")
        await engine.dispose()

    asyncio.run(migrate())
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "broken.json").write_text("{oops", encoding="utf-8")
    settings = Settings(_env_file=None, database_url=url, inbox_dir=inbox)  # type: ignore[call-arg]
    monkeypatch.setattr("app.cli.get_settings", lambda: settings)
    return settings


def test_seed_and_process_print_a_report(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["seed"])
    main(["process", "--mode", "replay"])
    first = capsys.readouterr().out
    main(["process", "--mode", "replay"])
    second = capsys.readouterr().out

    assert "Loaded 3 products" in first
    assert "Model mode: replay" in first
    lines = {line.split()[0]: line for line in first.splitlines() if line.startswith(("R", "un"))}
    assert "drafted -> draft ready_for_review" in lines["R1"]
    assert "duplicate" in lines["R4"]
    assert "Unusable input" in next(v for k, v in lines.items() if k.startswith("unusable-"))
    assert (
        "5 requests: 3 new drafts (1 ready_for_review, 2 needs_clarification), "
        "1 duplicate, 0 conflict, 1 failed, 0 already processed"
    ) in first
    # A rerun creates nothing and must not count the earlier drafts as new again.
    assert (
        "5 requests: 0 new drafts (none), 0 duplicate, 0 conflict, 1 failed, 4 already processed"
    ) in second


def test_live_mode_without_a_key_stops_with_a_clear_message(
    settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["process", "--mode", "live"])

    assert "MODEL_API_KEY is not set" in capsys.readouterr().err
