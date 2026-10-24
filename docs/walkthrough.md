# Walkthrough: approach and findings

The brief's presentation, written to be read in about five minutes. How to run it:
[README](../README.md). Every check, expected against observed:
[results/report.md](../results/report.md). How AI was used: [llm_usage.md](llm_usage.md).

## 1. The problem

Customers of a fictional distributor order by email. Some emails are clear ("Please send
2 individual CAB-1 cables"). Many are not: "Send two boxes of the usual cable" doesn't say
which cable, or how many cables a box holds. The app turns each email into a draft order for
staff to review. Anything unclear stays visible and gets a clarification draft; nothing is
guessed.

## 2. The approach: the model reads, code decides

The model does what code can't: read free text and look products up. It has one tool,
`search_catalog(query)`, which searches the local catalog, and it answers in a strict JSON
schema. Everything that has a right answer is decided in code: whether a search backs a
SKU, whether a quantity counts items, the price, duplicates, the status, and the
clarification text.

```
email ─► ingest ─► dedupe ─► model + search_catalog ─► validate ─► price ─► status ─► clarification
                    code      the only model step        code       code     code     code template
```

The brief is assessed on validation, ambiguity, duplicates and corrections. Those have to be
repeatable and testable, so none of them depends on the model's answer.

## 3. Decisions that matter

- **The model never sees the catalog.** Products are not in the prompt, so every SKU must
  come from a lookup. Each line names the search it relied on. Code keeps the SKU only if
  that search returned exactly that one product and the search shares a word with the
  line. "USB-C cables" matches CAB-1 and CAB-2 equally, so it stays ambiguous: the model
  lists both, and the clarification asks which one.
- **Quantities are never guessed.** "Two boxes", "2 packs" and "some" leave the quantity
  empty with a finding; box and pack sizes are never assumed.
- **Money is integer cents.** A line of 10 or more items gets `(line × 10 + 50) // 100` off,
  that line only. Pricing was written test-first, and an independent script re-checks every
  expected price with `Decimal`.
- **Duplicates are settled before the model is called.**
  - Same order reference and same text: a duplicate. No new draft, and it isn't counted as
    a new order.
  - Same reference, different text (R13: "make it 4 USB hubs instead of three"): nothing is
    merged, and the existing draft goes to *needs review* with both emails on the page. The
    rules say this is the same order, but not which version wins, so a person decides.
- **Two statuses, not one.** A request is *drafted*, *duplicate*, *conflict* or *failed*. A
  draft is *ready for review*, *needs clarification*, *needs review* or *reviewed*. *Ready
  for review* means structurally valid: every check passed. Only a person's **Mark
  reviewed** makes a draft *reviewed*.
- **A correction re-runs the checks, not the model.** A reviewer can set a line's SKU or
  quantity. Validation, pricing, status and the clarification re-run in code. The change is
  logged with the status before and after, and the model's original proposal is kept
  unchanged.
- **The app replays without an API key.** Every real model response is saved in `replays/`
  under a hash of what was sent, so a prompt change shows up as a visible miss instead of a
  stale answer. Every call is labelled `live`, `cached` or `simulated-failure`.

## 4. Demo, about two minutes

```bash
just install
just process
just run
```

Open http://127.0.0.1:8000.

1. **The queue.** 14 requests made 10 orders: 4 ready for review, 5 need clarification,
   1 needs review. 2 requests failed. The duplicate and the conflict are listed under *Not
   new orders*. Click a tile to filter.
2. **O3, "Send two boxes of the usual cable."** It has two findings: the cable could be
   CAB-1 or CAB-2, and boxes aren't items. The clarification draft asks both questions. The
   line has no price, so the total stays $0.00.
3. **O12, "Please send 10 USB-C cables."** Set line 1 to CAB-2 and save. The checks re-run:
   30,000 − 3,000 cents = $270.00, the status becomes *Ready for review*, and History
   records the change. Restart the server: the correction is still there. Then press
   **Mark reviewed**, and download the order from **Export** on the queue. The JSON has
   the line, the total and the history.
4. **O5.** The draft for 3 hubs, with R13's "make it 4" beside it, in *Needs review*.
5. **Failed.** O11 (request R11): its model call is labelled `simulated-failure`. The row
   with no order reference is R14, reported as an unusable file. Every other request was
   still processed.

## 5. Findings

- **Every check passes.** `just report` processes all 14 inputs on a fresh database from the
  replays, processes them again, applies the correction, and reads the result back as a
  restarted app would. All 19 of its checks match expectations worked out by hand from the
  rules before the app ran. The same checks run as tests on every commit.
- **Where the exceptions come from.** Half the orders (5 of 10) need clarification, for six
  reasons:
  - an ambiguous product, twice: R3 "the usual cable" and R12 "USB-C cables";
  - a box or pack count, twice: R3 and R10;
  - a vague amount, once: R9 "some";
  - an unknown product, once: R2 "Moon adapter".

  Every email that named a SKU, or a product the catalog has only one of, with a count of
  items, passed every check. R5 is held for review only because R13 changed it.
- **One practical improvement.** Ask customers for a SKU (or the cable length) and a number
  of individual items, in the order acknowledgement and on the order page. In this sample
  that removes 5 of the 6 clarification reasons. The sixth is a product the catalog doesn't
  sell.
- **Structurally valid is not reviewed.** After processing, 4 drafts are *ready for review*
  and none is *reviewed*. Passing the checks means a draft agrees with the catalog and the
  rules, not that a person has approved it. The export follows the same line: it contains
  only reviewed orders.

## 6. How AI was used, and what checking caught

Claude Code (Opus 5.5) wrote nearly all the code, tests, added data and docs, one reviewable
commit per step. I chose the task, the stack and the layout, reviewed each step, and
committed it myself. Inside the app, the model is `gpt-4.1-mini` at temperature 0.

Checking found real problems:

- **A loose SKU check.** At first a SKU only had to appear in *some* search of the same
  email, so a match for one item could justify another. Now each line names its own
  search. The prompt went to v2 and the replays were recorded again from the live API.
- **A rerun bug.** Processing the batch twice reported the old drafts as new. A CLI smoke
  test caught it; it is fixed, with a regression test.
- **A bug in the results report itself.** Its first version counted retried failed
  requests as new orders.
- **Three UI problems** that only clicking through in a browser showed.
- **From my code review.** Database errors are now domain errors. Routers are thin, and
  errors are handled in exception handlers.

Details: [llm_usage.md](llm_usage.md) and [ai-workflow/](../ai-workflow/README.md).

## 7. Limitations and next steps

- **Sample size.** 14 fictional emails show that each case is handled. They say nothing
  about accuracy on real email.
- **Review.** Conflicting requests are flagged, not merged. A reviewer can correct SKUs
  and quantities, but can't add or delete lines. There is one user, with no login or edit
  locking.
- **Search** is word matching over three products. A real catalog would need SQLite FTS5
  or embeddings behind the same tool.
- **Next steps:**
  - let a reviewer apply a conflicting request's change in one step;
  - show the model's proposal and the corrected order side by side;
  - run the same checks on a larger, messier set of emails, to measure the model rather
    than the code.
