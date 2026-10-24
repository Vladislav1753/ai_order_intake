# Order Intake — project instructions

## Project overview

Take-home assignment (Junior AI Engineer, alternative A, one working day). A local app for a
fictional distributor: turn customer order emails into **draft orders** for staff review and a
clear **queue of exceptions** (unknown product, ambiguous quantity, duplicate, failed processing).
A model interprets the text and looks up the catalog; code validates, prices, and decides status.
Nothing is sent anywhere: orders and clarification messages stay local drafts.

- Full brief: `docs/brief.md`. Rules that override everything else: `data/seed/domain.md`.
- Assessed on: validating drafts, flagging ambiguity, preventing duplicates, reviewer corrections,
  saved real model responses that replay without a key, and clear docs. Extra infrastructure
  earns nothing.

## Tech stack

Python 3.12 (uv) · FastAPI (async) · Jinja2 + HTMX · Pydantic v2 + pydantic-settings ·
SQLAlchemy 2.x asyncio (typed ORM) on SQLite via aiosqlite · Alembic (async env) · the model
provider's official SDK (async client) behind `LLMProvider` · pytest + pytest-asyncio · ruff ·
mypy · pre-commit. Ask before adding any other dependency.

## Architecture

```
routers ──► services ──► repositories ──► models (SQLAlchemy)
   │            │
templates   providers (LLMProvider: live SDK client | replay client)
```

| Package | Owns | Must not |
|---|---|---|
| `routers/` | HTTP, form parsing (Pydantic form models), rendering `templates/` | contain business rules, queries, or `try`/`except` |
| `services/` | business logic, transaction boundaries (one commit per request processed) | build SQL; call the SDK directly |
| `repositories/` | every SQLAlchemy query; take an `AsyncSession` | commit; contain business rules |
| `models/` | tables | contain behaviour beyond simple properties |
| `schemas/` | Pydantic I/O, form, and LLM output models | import ORM models |
| `providers/` | model clients implementing `LLMProvider` | know about orders or the DB |
| `core/` `db/` `api/` | settings, engine/session, FastAPI dependencies | — |

Dependencies are passed in (constructor or function args). The only module-level state is
settings. The engine is created inside the running event loop, by the app lifespan
(`app.state.sessionmaker`) or by the CLI's `asyncio.run` entry point, never at import time.

### Async rules

Everything that does I/O is `async def`: routes, services, repositories, providers.

- **Never block the event loop.** No `time.sleep`, sync HTTP clients, or sync DB drivers inside
  async code. Pure CPU work (pricing, validation) stays plain `def`. Use `asyncio.to_thread` for
  any unavoidable blocking call. Ruff's `ASYNC` rules catch the common cases.
- **One `AsyncSession` per task.** A session must never be shared between concurrent tasks.
- **No lazy loading.** Relationships are `lazy="raise"`; repositories eager-load what callers
  need with `selectinload`. `expire_on_commit=False`; never read attributes of an expired object
  (take ids before `expire_all()`).
- **Batch concurrency.** The batch runner groups requests by `order_ref`. Groups run concurrently
  in an `asyncio.TaskGroup`, capped by an `asyncio.Semaphore(max_concurrency)` (setting, default
  4, which respects provider rate limits). Requests inside a group run in input order, so dedupe
  is race-free and results match sequential processing. Each task opens its own session.
- **Timeouts.** Every provider call has a timeout (`model_timeout_s`). A timeout is a `failed`
  request; it never cancels the rest of the batch.
- SQLite runs in WAL mode with foreign keys on (`app/db/session.py`), so the UI can read while
  the batch writes.

### Processing one request (`IntakeService.process`)

1. **Ingest**: store the raw text, `order_ref`, source path, and SHA-256 content hash.
2. **Dedupe (code)**: an existing draft with the same `order_ref` and the same hash means
   `duplicate` and no new draft. The same `order_ref` with different text means `needs_review`
   (conflict). Duplicates never count as new orders.
3. **Extract (model)**: a bounded tool loop with one tool, `search_catalog(query)`, which only
   searches the local `products` table (`services/catalog.search_catalog`: word match on SKU and
   name, best score wins and every tie is returned; returns SKU + name, never prices). The budget is `catalog_search_budget` searches per request
   (setting, default 5) plus the final answer. An empty result tells the model to retry with a
   different query (shorter, synonym, SKU). The output is validated into `ExtractionResult`
   (Pydantic):
   - nothing found within the budget: the item is reported unmatched with its original wording,
     and code adds an `unknown_product` finding;
   - several candidates (e.g. "the usual cable" matching CAB-1 and CAB-2): the model lists them
     and never picks one; code adds an `ambiguous_product` finding.

   Invalid output, an exhausted step budget, a timeout, or an API error means `failed`, and the
   batch continues.
4. **Validate (code)**, per line: the line cites its search (`matched_query`), and that search
   from this run (kept in memory during `process`) must have returned exactly that SKU and
   share a non-digit word with the line's text, so a match for one item can't be reused for
   another. A SKU picked among tied results goes back to ambiguous; any other unsupported SKU
   is an `unverified_sku` finding. The reviewer may pick any catalog SKU later. The SKU must
   be in the catalog,
   and the quantity must be a positive int of individual items. Unit words such as "box" or
   "pack", and vague amounts, become findings.
5. **Price (pure function)**: see the domain rules.
6. **Status (code)**, two separate fields:
   - the request's outcome (`RequestStatus`): `drafted` · `duplicate` · `conflict` · `failed`
     (`pending` until processed). Duplicates and conflicts never create a draft; a conflict marks
     the existing draft `needs_review` with a `conflicting_request` finding.
   - the draft's state (`DraftStatus`): `ready_for_review` · `needs_clarification` ·
     `needs_review` · `reviewed`. `reviewed` is set only by an explicit reviewer action.
7. **Clarification**: a code template built from the findings (e.g. "Which cable: CAB-1 or CAB-2?"),
   stored in `draft_orders.clarification_text`.
8. Save everything in one transaction, including the request's `model_calls` list.

**Reviewer correction** (`ReviewService.correct`): apply the field change, re-run validate +
price + status (no model call), and append a `corrections` row (field, old, new, status before
and after). Only a line's `sku` (a catalog SKU) and `quantity` (individual items) change; an
empty value reopens the field. Findings the checks can't re-derive carry over:
`conflicting_request` stays, `unverified_sku` goes once the reviewer sets that line's SKU.
`ReviewService.mark_reviewed` is the explicit sign-off: refused while the draft needs
clarification, logged as a `status` row, and undone by any later correction.
`ExportService.reviewed` (`GET /exports/reviewed.json`) exports `reviewed` drafts only, never
ones that merely passed the checks.

### Tables

Models live in `app/models/` (`product.py`, `request.py`, `draft.py`); enums in `app/core/enums.py`.

Five tables. Keep it that way: derived or never-queried data goes in a JSON column (typed by a
Pydantic schema in `schemas/`), not a new table.

- `products`: the catalog, loaded from `data/seed/seed.json` by a seed command.
- `requests`: one row per customer message (`external_id` unique, `order_ref`, text, hash,
  outcome). Linked to its draft through `order_ref`, not a foreign key. `model_calls` (JSON
  list): every provider round trip, raw (step, `source`: `live` | `cached` |
  `simulated-failure`, prompt version and hash, request, response or error), including the
  catalog searches and their results.
- `draft_orders`: one per `order_ref` (unique), with totals, `proposal_json` (the model's
  validated output, written once and never updated), `findings` (JSON list, replaced on every
  validation) and `clarification_text`.
- `draft_lines`: `sku` (FK to `products.sku`) and `quantity` stay NULL when they need
  clarification.
- `corrections`: append-only reviewer edits with status before and after.

Timestamps use `UTCDateTime` (`app/db/types.py`), enums use `str_enum()`. Schema changes go
through Alembic only: edit the models, run `just revision "<message>"`, review the generated
file, and keep `tests/integration/test_migrations.py` passing (it fails when models and
migrations drift apart).

## Domain rules (source of truth: `data/seed/domain.md`)

- Money is integer USD cents with a `_cents` suffix. Never use `float` or `round()` for money.
- Lines with >= 10 items: `discount_cents = (line_cents * 10 + 50) // 100`, on that line only.
  There are no other charges.
- Never infer box or pack sizes. Unknown products and ambiguous quantities need clarification,
  never a guess.
- The same `order_ref` is the same order. Reprocessing an identical request creates no new draft.
- Unclear rule: record it in README "Assumptions and ambiguities". Do not invent policy.

## Model boundaries

- The model interprets text and calls `search_catalog`. It never prices, sets a status, or
  decides duplicates.
- Reject any SKU that was not returned by `search_catalog` for the same request.
- Prompts live in `app/providers/prompts/` with a `PROMPT_VERSION`; temperature 0.
- The schema parts of the prompt are generated, never hand-written: the tool's input schema
  and the output format come from the Pydantic models (`model_json_schema()`), and the catalog
  description (fields, what the search matches on) comes from the `Product` model. Catalog
  rows are never put in the prompt: the model must look products up, which is what makes the
  "SKU came from a lookup" check meaningful. The rendered prompt's hash is stored with each
  model call, so a schema change shows up as a replay miss instead of a silent mismatch.
- `MODEL_MODE=replay` runs the whole app from `replays/` without an API key. Tests never touch
  the network.

## Coding conventions

- Full type hints; `mypy app scripts` is clean. SQLAlchemy uses `Mapped[...]` / `mapped_column`.
- Route decorators declare `status_code=HTTPStatus.<NAME>` and `response_model=` (JSON) or
  `response_class=` (`HTMLResponse` pages; `RedirectResponse`, where the route returns the
  URL). No bare status numbers anywhere.
- Enums are `StrEnum`. Timestamps are timezone-aware UTC. IDs are integers in the DB; external
  request IDs are kept as given.
- **Errors.** Domain errors live in `app/core/errors.py` (`DomainError`: `NotFoundError`,
  `AlreadyExistsError`, `InvalidDataError`, `StorageUnavailableError`). Library exceptions don't
  cross layers: every async repository method has `@translates_db_errors`, and services wrap
  `session.commit()` in `translate_db_errors()` (`app/db/errors.py`). Routers stay thin and
  catch nothing: exception handlers in `app/api/handlers.py` turn domain errors into HTTP
  statuses, and a change rejected on the draft page (`InvalidDataError` or invalid form input)
  into that page again with the reason (422). The batch turns any error into a `failed` result for that request
  only. Anything that is not a `DomainError` is a bug: let it propagate, never swallow it.
- Use stdlib `logging`, not `print` (scripts excepted). No commented-out code.
- Docstrings only where intent is not obvious from names. Keep functions small and single-purpose.
- Name things after the domain: `order_ref`, `unit_cents`, `line_cents`, `findings`.

## Testing and quality bar

pytest-asyncio runs in auto mode: write tests as plain `async def test_...`, no marker needed.

- `tests/unit/`: pure logic (pricing, validation, dedupe, status) with no DB.
- `tests/integration/`: services and repositories on a temporary, freshly migrated SQLite DB
  (`session` fixture) with the replay or a fake provider.
- `tests/web/`: routers through the `client` fixture (`httpx2.AsyncClient` + `ASGITransport`,
  with the app lifespan running).
- `tests/acceptance/`: the five minimum-demonstration checks from the brief. They read
  expectations from `data/expected/`, which are computed independently and never copied from
  app output.
- Write pricing and validation test-first. Every bug fix gets a regression test.
- A step is done only when `uv run pre-commit run --all-files` passes (frozen-seed guard, ruff
  format, ruff check, mypy, pytest).

## Workflow (step-by-step, small commits)

1. Work one logical step at a time (e.g. models + migration, then a repository, then a service
   with its tests, then routers). Don't start the next step unprompted.
2. Finish each step by running `uv run pre-commit run --all-files`. Untracked files are skipped,
   so `git add` the step's files first; staging is fine, committing is not.
3. Report the gate result, the list of changed files, and a proposed commit message in
   Conventional Commits form, `type(scope): imperative summary`, at most 72 characters (types:
   feat, fix, test, refactor, docs, chore, data).
4. **The user commits.** Claude never runs `git commit` or `git push` (denied in
   `.claude/settings.json`).

Build order: models + migration → repositories → pricing/validation (test-first) → provider
(live + replay) → intake service → CLI `process` → queue page → detail + correction →
acceptance tests + results report → docs.

## Windows environment

- The dev machine runs Windows 11, and the user path contains Cyrillic characters.
- The Bash tool runs Git Bash: use forward slashes and POSIX syntax. PowerShell is separate.
- Commands given to the user to run are for Windows PowerShell 5.1: no `&&`; chain with
  `; if ($?) { ... }` or put each command on its own line.
- Run Python only via `uv run python` / `uv run <tool>`. `python3` is a Microsoft Store stub here.
- Don't use `rm -rf` / `Remove-Item` (blocked by the sandbox). Ask the user to delete things.
- Read and write files as UTF-8 explicitly (`encoding="utf-8"`).

## Never

- Edit `data/seed/`. It is frozen and guarded by a deny rule and a pre-commit hook.
- Use application output as expected results.
- Read or commit `.env`, API keys, or the SQLite DB under `var/`.
- Hardcode answers for the seed requests.

## Commands

Recipes live in `justfile` (`just` lists them). Use just, not make: the Chocolatey make on
this machine garbles the Cyrillic user path in child environments, so uv fails under it. When
a step adds a command (migrations, seeding, processing the inbox), add a recipe for it too.

```
just install      # uv sync + pre-commit install + migrate + seed
just run          # uv run uvicorn app.main:app --reload
just test         # uv run pytest
just check        # uv run pre-commit run --all-files
just migrate      # uv run alembic upgrade head
just seed         # uv run python -m app.cli seed (catalog from data/seed/seed.json)
just process      # process seed requests + data/inbox from replays/ (no key needed)
just record       # same with real model calls; saves each response to replays/
just check-data   # check data/expected against inputs and rules (independent of the app)
just report       # write results/report.md (expected vs observed, fresh DB, from replays)
just revision "<message>"   # uv run alembic revision --autogenerate -m "<message>"
```

The starter-pack skill `.claude/skills/generate-assignment-data` is for Claude: run it in the
data step to extend `data/inbox/` and `data/expected/`. It refers to `tasks/orders/`; in this
repo those files are in `data/seed/`. The user hand-checks the 5 reference cases it lists;
never fill those in from app output.
