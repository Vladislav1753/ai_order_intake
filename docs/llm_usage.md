# LLM usage note

## Tools and models

| Where | Tool | Model and settings |
|---|---|---|
| Development | Claude Code 2.1.308, Claude desktop app (Code tab), on Windows 11 | `claude-opus-5-5` (setting `opus[1m]`), effort `high`, defaults otherwise |
| Development | Context7 MCP server (library docs) | current docs for FastAPI, SQLAlchemy 2, Alembic, pytest-asyncio, the OpenAI Python SDK and htmx, instead of answering from memory |
| Development | The desktop app's built-in browser | to click through the review screens and check console errors |
| Development | Project skill `generate-assignment-data` (from the starter pack) | used once, in the data step |
| Application | OpenAI Chat Completions, official async SDK `openai` 3.37 | `gpt-4.1-mini`, temperature 0, 1,024 output tokens, 60 s timeout, 5 catalog searches per email |

The full inventory, with paths, versions, redactions and what was not used, is in
[ai-workflow/README.md](../ai-workflow/README.md) and
[ai-workflow/manifest.json](../ai-workflow/manifest.json).

## What was generated

Claude Code wrote nearly all files: the application code, the migration, the tests, the
added fictional data and expected results, the check scripts, and the docs. The prompt for
the application's model is in `app/providers/prompts/extract_system.md`.

The candidate made the decisions and reviewed every step:

- chose alternative A and the stack (FastAPI, Pydantic, SQLAlchemy, SQLite, HTMX);
- asked for the layered layout (routers, services, repositories, models, schemas);
- set the workflow: one small, reviewable commit per step;
- reviewed each step and committed it themselves. The agent is denied `git commit` and
  `git push` in `.claude/settings.json`.

The rules the agent followed are in `CLAUDE.md`: architecture, domain rules, what the model
may decide, and the quality gate. The candidate checked the five reference cases by hand
(`data/expected/reference-cases.md`).

## A representative instruction

> Build the review service (correction with re-validation, saved history) and the queue and
> detail pages, and un-skip C1.

What shaped the result:

- `CLAUDE.md` fixed the layering, async rules, the five tables, and the rule that a
  correction re-runs validation without a model call.
- `data/expected/expected-results.json` already held the hand-derived C1 expectation
  (30,000 − 3,000 = 27,000 cents, *needs clarification* → *ready for review*).

How it was checked:

1. **The gate** (`uv run pre-commit run --all-files`): ruff, mypy and 124 tests, including
   the un-skipped C1 acceptance test. That test posts the correction through the web form,
   restarts the app, and compares the saved draft and its history with the expectation.
2. **A mutation check.** Removing the re-validation call made C1 fail, so the test catches it.
3. **A browser check of the real pages**, which found three problems the tests had not:
   - the order table was cramped;
   - boosted links kept the old scroll position;
   - a rejected change left the form's URL in the address bar.

   All three were fixed and re-checked.

## Corrections and improvements

- **Candidate review: error handling.** After the repositories were written, the candidate
  asked: *"where is error handling in repositories? db errors and etc. i wanted to handle
  them with domain errors we create"*. Database errors are now translated into domain
  errors (`app/db/errors.py`) and mapped to HTTP statuses, with tests.
- **Candidate review: thin routers.** The draft routes caught errors themselves. On the
  candidate's request, error handling moved to exception handlers (`app/api/handlers.py`).
  Every route now declares `status_code=HTTPStatus.…` with `response_model` or
  `response_class`.
- **Checking found the agent's own bugs:**
  - A CLI smoke test showed that re-running the batch reported the old drafts as new again.
    Fixed with an `already_processed` flag and a regression test.
  - The results report's first run flagged a failure in its own metric: it counted the
    retried failed requests as new orders. The app had created no extra order.
- **Not taking the model's word for it.** The first check only required a SKU to appear
  in some search of the same request, so a match for one item could be reused for another.
  Every line now cites its own search, which must have returned exactly that product and
  share a word with the line. The prompt went to v2 and the replays were re-recorded from
  the live API. A later live run on all 14 inputs matched the hand-derived expectations.

Expected results are never taken from the application. `scripts/check_expected.py`
re-checks them with independent arithmetic, and a deliberately broken expectation was
confirmed to fail it.
