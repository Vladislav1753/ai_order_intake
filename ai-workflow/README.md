# AI workflow used during this exercise

Machine-readable inventory: [manifest.json](manifest.json). Short usage note for the
brief: [docs/llm_usage.md](../docs/llm_usage.md).

## Tools and models

**Development (writing the code).**

| Tool | Version, model, settings | Status |
|---|---|---|
| Claude Code in the Claude desktop app (Code tab), Windows 11 | Claude Code 2.1.308; model `claude-opus-5-5` (user setting `opus[1m]`); effort `high`; other settings default | used |
| Context7 MCP server (HTTP, user scope) | `https://mcp.context7.com/mcp`; API key header redacted | used: docs for FastAPI, SQLAlchemy 2, Alembic, pytest-asyncio, OpenAI Python SDK, htmx |
| Built-in browser pane of the desktop app | default; dev server from `user-level/launch.json` | used: clicking through the review screens |
| Inline diagrams (desktop app visualizer) | default | used: diagrams explaining the data flow to the candidate (no code) |
| Project skill `generate-assignment-data` | from the starter pack, unchanged | used once, in the data step |
| Plugin `understand-anything` | installed at user level | not-used |
| Claude in Chrome, web search, subagents | available | not-used |
| Claude.ai connectors (Claude Docs, Google Drive) | connected at account level | not-used |
| uv, just, pre-commit, Python | uv 0.8.9, just 1.59.0, pre-commit 4.7.0, Python 3.12.11 | used |

Three Claude Code sessions did the work:
1. **Planning** (2026-10-23): reading the starter pack and choosing alternative A, the stack,
   the layout and the commit-per-step workflow.
2. **Build** (2026-10-23 to 2026-10-24): every commit.
3. **A fork of the build session** (2026-10-24), which the candidate used to have the data
   flow explained. It changed no files.

**Application (the model inside the app).** OpenAI Chat Completions through the official
async SDK (`openai` 3.37):

- model `gpt-4.1-mini` (the responses report `gpt-4.1-mini-2025-04-14`);
- temperature 0, `max_completion_tokens` 1024, 60 s timeout, 1 SDK retry;
- up to 5 `search_catalog` calls per email, then a forced final answer.

Settings live in `app/core/config.py` and are overridable through the environment
variables listed in [.env.example](.env.example).

## Configuration files

Project configuration, in its normal repository location (earlier versions are in Git
history):

| Path | Purpose | Versions |
|---|---|---|
| `CLAUDE.md` | Agent instructions: architecture, async rules, domain rules, model boundaries, conventions, workflow (the agent never commits) | added in `5e3195d`, extended in later commits: `git log -- CLAUDE.md` |
| `.claude/settings.json` | Permissions. Allows the test, lint, type-check, migration and read-only git commands. Denies reading `.env`, editing `data/seed/**`, `git commit` and `git push` | unchanged since `5e3195d` |
| `.claude/skills/generate-assignment-data/SKILL.md` | Starter-pack skill for extending the fictional data | unchanged since `5e3195d` |
| `.pre-commit-config.yaml` | Git pre-commit hook: frozen seed, expected-data check, ruff format, ruff check, mypy, pytest | `8324faa`, extended in `6f1d064` |
| `scripts/check_frozen_seed.py` | Hook script: fails if `data/seed/` differs from the committed starter pack | `8324faa` |
| `scripts/check_expected.py` | Hook script: re-checks `data/expected/` against inputs and rules with its own arithmetic | `6f1d064` |
| `app/providers/prompts/extract_system.md` | System prompt of the application's model (`extract-v2`) | v1 in `25941fa`, v2 in `1a2c8b9` |
| `app/core/config.py`, `.env.example` | Application model settings and their environment variable names | — |
| `replays/` | Saved real model responses; `simulated-failures.json` marks R11's deliberate failure | `1a2c8b9`, `6f1d064` |

User-level configuration, as sanitized snapshots in [user-level/](user-level/):

| Snapshot | Original location | Why it is relevant | Redactions |
|---|---|---|---|
| `user-level/CLAUDE.md` | `~/.claude/CLAUDE.md` | Windows rules (Cyrillic user path, no `rm -rf`), version-pinning rule | none |
| `user-level/rules/context7.md` | `~/.claude/rules/context7.md` | makes the agent look up library docs through Context7 | none |
| `user-level/memory/user-shell-powershell.md` | Claude Code auto-memory for this folder | commands for the candidate in PowerShell 5.1 syntax | session id removed |
| `user-level/settings.excerpt.json` | `~/.claude/settings.json`, user-scope MCP config | model, effort, enabled plugin, Context7 server | Context7 API key replaced by `<redacted>` |
| `user-level/launch.json` | `D:/.claude/launch.json` (session folder) | starts the app on a scratch database for the browser check | machine paths replaced by `<repo>`, `<scratch-dir>` |

Deliberately left out because they are unrelated to this exercise:
- the rest of `~/.claude/settings.local.json`: permissions for other work, such as Docker
  and other websites;
- `D:/.claude/settings.local.json`: permissions for another project;
- another auto-memory note about an unrelated project.

No Claude Code hooks, custom agents or subagent definitions were used. The only hooks are
the Git pre-commit hooks above.

## One workflow example

The instruction:

> Build the review service (correction with re-validation, saved history) and the queue and
> detail pages, and un-skip C1.

**Configuration that shaped it:**
- `CLAUDE.md`: layering, async rules, "a correction re-runs validation without a model call",
  one step per commit.
- `.claude/settings.json`: the agent can run the gate, but can't commit.
- The Context7 rule: htmx 2 and FastAPI docs were looked up before use.
- The hand-derived C1 expectation in `data/expected/expected-results.json`:
  ```json
  "change": {"line": 1, "field": "sku", "from": null, "to": "CAB-2"},
  "status_before": "needs_clarification", "status_after": "ready_for_review",
  "subtotal_cents": 30000, "discount_cents": 3000, "total_cents": 27000
  ```

**Checking:**
- **The gate:** 124 tests, including the C1 acceptance test. That test posts the correction
  through the form, restarts the app, and compares the saved draft and history with the
  expectation above.
- **A mutation check:** without the re-validation call, C1 fails.
- **A browser pass** found three UI problems (a cramped table, a lost scroll position, the
  wrong URL after a rejected change). They were fixed and re-checked.

**Correction by the candidate afterwards:** the draft routes caught errors themselves. On
request, error handling moved into exception handlers (`app/api/handlers.py`), and every
route now declares `status_code=HTTPStatus.…` with `response_model` or `response_class`.
More corrections are in [docs/llm_usage.md](../docs/llm_usage.md).

## Reproduce or replay

**Run the application without credentials.** Needs Python 3.12, uv, and optionally just:

```bash
just install   # or: uv sync; uv run pre-commit install; uv run alembic upgrade head; uv run python -m app.cli seed
just process   # or: uv run python -m app.cli process --mode replay
just run       # or: uv run uvicorn app.main:app --reload
just report    # or: uv run python -m scripts.results_report
```

`MODEL_MODE=replay` is the default. Every response comes from `replays/` and is labelled
`cached`; R11's failure is labelled `simulated-failure`. Live calls (`just record`) need
`MODEL_API_KEY` in `.env`. Copy the variable names from `../.env.example`.

**The Git hook.** `uv run pre-commit install` adds a pre-commit hook that runs on every
`git commit`. It checks that `data/seed/` is unchanged and that `data/expected/` still
matches the inputs and rules, then runs ruff, mypy and pytest. Read
`.pre-commit-config.yaml` before installing it. `just check` runs the same checks by hand.

**Restoring the development setup.**
- **Project configuration:** `CLAUDE.md` and `.claude/` are already in place; Claude Code
  reads them when started in the repository folder.
- **User-level files:** copy `user-level/CLAUDE.md` and `user-level/rules/context7.md` to
  `~/.claude/`.
- **Settings:** merge `user-level/settings.excerpt.json` into `~/.claude/settings.json`.
- **Context7:** add the server with
  `claude mcp add --header "CONTEXT7_API_KEY: <your key>" --transport http context7 https://mcp.context7.com/mcp`.
- **Browser check:** put `user-level/launch.json` in the folder where the session is
  opened, with real paths.

## Decisions and limitations

- **One agent, step by step.** One Claude Code session built everything, one reviewable
  commit at a time, with the candidate committing. That kept every change small enough to
  read and explain. Parallel agents would have saved little on a one-day task and made
  review harder.
- **Guard rails instead of extra tooling.** The pre-commit gate, the frozen-seed check, the
  independent expected-data check and the deny rules caught mistakes. No custom agents or
  Claude Code hooks were needed.
- **Context7** stopped answers from outdated memory. For example, it confirmed the htmx 2
  `responseHandling` setting and FastAPI's redirect `response_class` pattern before use.
- **What I would change:**
  - Run `/code-review` before each commit for a second opinion.
  - Add a project hook that runs `just check-data` whenever the agent edits `data/`; today
    that only happens at commit time.
