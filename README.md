# Order Intake & Exception Handling

Take-home alternative A (starter pack version 2026-10-02, see `data/seed/pack-version.json`).

A local app for a fictional distributor. It turns customer order emails into **draft orders**
for staff review and a **queue of exceptions**: unknown products, ambiguous products or
quantities, duplicate and conflicting requests, and failed processing. A model reads the
email and looks products up in the local catalog; code validates, prices, and decides every
status. Nothing is sent anywhere: orders and clarification messages stay local drafts.

**Result:** all five minimum-demonstration checks and all 14 inputs match the
independently derived expectations ([results/report.md](results/report.md)), from saved
real model responses, with no API key.

**Presentation:** a written walkthrough of the approach and findings is in
[docs/walkthrough.md](docs/walkthrough.md).

## Quick start

Needs Python 3.12, [uv](https://docs.astral.sh/uv/), and optionally
[just](https://github.com/casey/just) (`winget install --id Casey.Just -e`). No API key is
needed: the app replays saved real responses from `replays/`.

```bash
just install    # uv sync, pre-commit hook, migrate var/orders.db, load the catalog
just process    # process the 4 seed requests and the 10 in data/inbox/ from replays
just run        # http://127.0.0.1:8000
```

Copy `.env.example` to `.env` only if you want to change a setting; the defaults work.

Then, in the browser:

1. The queue shows counts per status. Click a tile or a filter.
2. Open **O12** ("10 USB-C cables": CAB-1 or CAB-2?). On line 1 choose **CAB-2** and press
   **Save SKU**. The checks re-run: the total becomes $270.00 (bulk discount included), the
   status becomes *Ready for review*, and History records the change.
3. Stop the server and run `just run` again: the correction is still there.
4. **Mark reviewed** signs the draft off. It is refused while a draft needs clarification.
5. On the queue, **Export → Reviewed orders (JSON)** downloads every signed-off order.
6. Under *Failed*, **O11** shows the simulated model failure and how its call is labelled.

Other commands (`just` lists them all):

| Recipe | Plain command | What it does |
|---|---|---|
| `just test` | `uv run pytest` | unit, integration, web and acceptance tests |
| `just check` | `uv run pre-commit run --all-files` | the full gate: frozen seed, expected data, ruff, mypy, pytest |
| `just check-data` | `uv run python scripts/check_expected.py` | re-checks `data/expected/` against the inputs and rules, independently of the app |
| `just report` | `uv run python -m scripgit commit -m "feat(export): add reviewed-orders JSON export and written walkthrough"ts.results_report` | rewrites `results/report.md` from a fresh run |
| `just record` | `uv run python -m app.cli process --mode live` | real model calls; saves each response to `replays/` (needs `MODEL_API_KEY`) |
| `just migrate` / `just seed` / `just process` | `uv run alembic upgrade head`, `uv run python -m app.cli seed`, `uv run python -m app.cli process --mode replay` | the steps `install` and `process` run |

`just process` and `just record` are safe to rerun: requests already processed are skipped,
and only failed ones are retried. To start over, delete `var/orders.db` and run
`just install` again.

## Architecture

```
data/seed/seed.json, data/inbox/*.txt|*.json
        │  app/services/inbox.py: read files; unusable files are reported, not fatal
        ▼
IntakeService.process  (one request, one transaction)
  1. ingest      store the raw text, order_ref, source file, SHA-256 of the text
  2. dedupe      same order_ref + same text → duplicate; different text → conflict
  3. extract     model + search_catalog tool, ≤ 5 searches     ← the only model step
  4. validate    every SKU must be backed by a search from this run
  5. price       integer cents, bulk discount per line
  6. status      request outcome and draft status, set by code
  7. clarify     a templated message built from the findings
        ▼
SQLite (var/orders.db) ──► FastAPI + Jinja2 pages: queue, draft, request
                                 ├─ ReviewService: correct a line, re-run 4–7, log it
                                 └─ ExportService: signed-off drafts as JSON
```

Layers: `routers/` (HTTP, forms, templates) → `services/` (business logic, one commit per
action) → `repositories/` (every query) → `models/` (five tables). The model client sits
behind `LLMProvider` in `providers/`: a live OpenAI client, a replay client, and a wrapper
that injects simulated failures. Everything is async; the batch processes different orders
concurrently (up to `MAX_CONCURRENCY`, default 4) and requests for the same order in input
order, so deduplication can't race. Details: [CLAUDE.md](CLAUDE.md).

**What the model may and may not do.** It reads the email and calls one tool,
`search_catalog(query)`, which only searches the local `products` table and returns SKU and
name, never prices. Catalog rows are never put in the prompt, so every SKU has to come from
a lookup. Its final answer is a strict JSON schema generated from Pydantic
(`ExtractionResult`): per line the customer's words, the search it relied on
(`matched_query`), the SKU or the candidate SKUs, the number, and the unit (item, box, pack).
Code then decides:

- A SKU is kept only if the cited search returned exactly that one product and shares a
  word with the customer's text for that line. A SKU picked among tied results goes back to
  *ambiguous*; any other unsupported SKU is an `unverified_sku` finding.
- Quantities must be a positive number of individual items. Boxes, packs and vague amounts
  ("some") become findings; box and pack sizes are never assumed.
- Prices come from the catalog: `line = quantity × unit price`; a line of 10 or more items
  gets `discount = (line × 10 + 50) // 100` (10%, halves up).
- Invalid output, a refusal, a timeout, an unavailable provider, or no answer within the
  step budget makes the request `failed`; the rest of the batch continues.

**Statuses.** A request ends as `drafted`, `duplicate`, `conflict` or `failed`. A draft is
`ready_for_review` (every check passed: structurally valid), `needs_clarification` (a
question for the customer), `needs_review` (a conflicting request or an unverified SKU),
or `reviewed`, which only a person sets with **Mark reviewed**. Duplicates and conflicts
never create an order and are not counted as new orders.

**Reviewer corrections.** A reviewer can set a line's SKU (catalog only) or its quantity, or
clear either. Validation, pricing, status and the clarification draft re-run without a model
call. Each change is saved as a `corrections` row (field, old, new, status before and
after), shown under History. The model's original proposal (`proposal_json`) is never
changed, so the page shows what the model proposed next to the correction. A correction
after sign-off removes the sign-off.

**Export.** `GET /exports/reviewed.json` (the queue's *Export* link) downloads every
reviewed draft as JSON. Each order has its lines, prices and totals, the source request and
any later ones, the findings the reviewer signed off, and the history. A draft that only
passed the checks is not exported: the file holds only what a person approved.

**Tables** (Alembic migration in `migrations/`): `products`, `requests` (raw text, outcome,
every model call with its source label), `draft_orders` (one per order reference, totals,
findings, clarification, proposal), `draft_lines`, `corrections`.

## Model configuration

| Setting | Value | Why |
|---|---|---|
| Provider, API | OpenAI Chat Completions, official async SDK (`openai` 3.37) | tool calling plus strict structured outputs in one API |
| `MODEL_NAME` | `gpt-4.1-mini` (responses report `gpt-4.1-mini-2025-04-14`) | cheap, fast, reliable with tools and JSON schemas; the task is extraction, not reasoning |
| `MODEL_TEMPERATURE` | 0 | repeatable answers |
| `MODEL_MAX_TOKENS` | 1024 | an answer is a few lines of JSON |
| `MODEL_TIMEOUT_S` | 60 per call, 1 SDK retry | a hung call fails that request only |
| `CATALOG_SEARCH_BUDGET` | 5 searches per email, then the answer is forced | bounds cost and loops |
| Prompt | `app/providers/prompts/extract_system.md`, version `extract-v2` | the tool and output schemas are generated from Pydantic, not hand-written |

`MODEL_MODE=replay` (the default) serves responses from `replays/`; `live` calls the API and
saves each response there. All settings are environment variables (see `.env.example`); the
key is only read from `.env`, which is git-ignored.

## Replay without an API key

Each model round trip is saved as `replays/<request>.<step>.<hash>.json` with the full
request and the raw response. The hash covers the messages sent, which include the rendered
prompt, so a prompt or schema change shows up as a replay miss (the request fails visibly)
instead of a silently mismatched answer. Every call stored in the database carries a label:

- `live`: a new call to the provider, made by `just record`;
- `cached`: a saved real response, replayed (everything you see after `just process`);
- `simulated-failure`: a deliberate failure from `replays/simulated-failures.json` (R11 only).

The committed replays are real `gpt-4.1-mini` responses recorded on 2026-10-24 for the 10
requests that reach the model (R4 and R13 are settled in code before any model call, R14 is
unreadable, and R11's call fails on purpose); the live run matched every expectation. To record again, set
`MODEL_API_KEY` in `.env`, point `DATABASE_URL` at a new database file (requests already
processed are skipped), run `just migrate`, `just seed` and `just record`.

## Data, reference cases and results

- **Inputs**: the 4 seed requests (unchanged, guarded by a pre-commit hook) and 10 added
  requests in `data/inbox/` (9 emails, 1 JSON in the template's shape), written by hand with
  the starter pack's `generate-assignment-data` skill. No randomness. Coverage, generation
  method and the deliberately invalid input: [data/README.md](data/README.md).
- **Expected results**: `data/expected/expected-results.json`, derived from `domain.md`
  before the app ran on the new requests, never copied from its output.
  `scripts/check_expected.py` re-checks every price, id and count with its own code.
- **Five reference cases** with hand arithmetic, for a person to verify:
  [data/expected/reference-cases.md](data/expected/reference-cases.md).
- **Results**: [results/report.md](results/report.md), generated by `just report`; the same
  checks run in `tests/acceptance/` on every commit.

| Minimum demonstration check | Case | Result |
|---|---|---|
| A normal request becomes the expected draft; prices match the checked reference | R7: 10 × CAB-1 (18,000 after the 2,000 discount) + 1 × HUB-1 (5,000) = 23,000 cents | pass |
| An unknown product stays unresolved, with a useful clarification draft | R2 "one Moon adapter": no SKU, asks for the SKU or full name | pass |
| An ambiguous quantity is flagged, not guessed | R10 "2 packs of CAB-1", R9 "some HUB-1 hubs": no quantity, needs clarification | pass |
| Processing the duplicate again creates no second order and doesn't inflate the count | R4 = R1: duplicate; 10 orders from 14 requests; a second full run adds 0 | pass |
| A reviewer correction changes the saved draft, re-runs the checks, survives a restart | C1: O12 line 1 → CAB-2: 30,000 − 3,000 = 27,000, ready for review, history saved | pass |

No check failed.

## What the results suggest: one practical improvement

After processing, 5 of the 10 orders need clarification, for six reasons: an ambiguous
product twice (R3 "the usual cable", R12 "USB-C cables": both are cables with no length),
a box or pack count twice (R3, R10), a vague amount once (R9 "some"), and an unknown product
once (R2). Every request that named a SKU or a product the catalog has only one of, with a
count of items (R1, R5, R6, R7, R8), passed every check; R5 is held for review only because
R13 changed it.

So the cheapest improvement is upstream: **ask customers for a SKU (or the cable length) and
a number of individual items** in the order-acknowledgement template and on the order page.
In this sample that would have prevented 5 of the 6 clarification reasons; R2's product is
simply not sold. A second step, if the business wants it: give the catalog an explicit pack
size per product so pack orders can be converted by rule; today the rules forbid guessing
one.

## Assumptions and ambiguities

From the data step ([data/README.md](data/README.md)):

- **A1 Packs** are treated like boxes: the item count needs clarification.
- **A2 Vague amounts** ("some") are ambiguous quantities; no default is used.
- **A3 Same order, different text** (R13): rule 4 says it is the same order but not what to
  do when the content differs. No new draft is made, nothing is merged, and the existing
  draft is flagged `needs_review` with the other request shown beside it. Its totals stay
  as drafted from the first request until a reviewer corrects them.
- **A4** C1's customer reply is fictional; there is no inbound reply channel.

From the implementation:

- **A5** Matching by "an unambiguous catalog description" (rule 3) is done by word overlap
  with SKU and name; ties are ambiguous, never resolved by the model.
- **A6** A reviewer corrects SKUs and quantities only (the fields that decide the price); a
  line's customer text and unit are kept as received.
- **A7** A failed request is retried on the next run; anything else processed is final.
- **A8** An unreadable input file gets the id `unusable-<file>-<hash>` and is listed as
  failed with the reason.

## Optional enhancements

| From the brief | Status |
|---|---|
| Export reviewed draft orders in a simple structured format | done: the JSON export above |
| A clearer comparison between the model proposal and the reviewer's correction | partly: a changed SKU or quantity shows the model's value under it, and History lists each change with the status before and after; there is no side-by-side view of the whole order |
| One more request format, such as an image attachment | not done: it needs a vision call, new data and new expectations, which didn't fit the time left |

## Known limitations

- **Edited inputs.** A request id already processed is skipped even if its file text
  changed; a fixed unusable file leaves its old failed row behind.
- **Retrying empty searches is prompt-guided, not enforced.** For R2 the model searched
  once and then reported the product unknown. The outcome is right, but code does not force
  a second query.
- **Search** is a word match over an in-memory list: fine for 3 products; a real catalog
  would want SQLite FTS5 or embeddings, still behind the same tool.
- **Review is single-user**: no login, no locking against two people editing one draft,
  no adding or deleting lines, and conflicts are flagged, not merged.
- **Parallel processing** is used by the batch but has no dedicated concurrency test.
- **The pages load htmx from a CDN**; without network they still work as plain forms.
- **14 fictional requests** show that each case is handled; they say nothing about the
  model's accuracy on real email.

## Time spent

**~7-7.5 hours**

Commit timestamps span 2026-10-23 16:14 to
2026-10-24 (Git history shows the order of the steps).

## AI usage

See `docs/llm_usage.md` and `ai-workflow/`.
