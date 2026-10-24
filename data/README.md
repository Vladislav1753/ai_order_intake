# Dataset

All data is fictional. Prices are integer USD cents.

| Path | What | Source |
|---|---|---|
| `seed/` | Catalog (3 products), 4 seed requests, domain rules, supplied expectations | Starter pack, unchanged (frozen by a pre-commit hook) |
| `inbox/` | 10 more requests: 9 short emails (`.txt`) and 1 in the template's JSON shape | Added for this exercise |
| `expected/expected-results.json` | Expected outcome of all 14 requests and 1 reviewer correction | Derived by hand from `seed/domain.md` |
| `expected/reference-cases.md` | The 5 reference cases, with hand arithmetic, for a person to check | Same |
| `../replays/simulated-failures.json` | Request R11 is failed on purpose, labelled `simulated-failure` | Added for this exercise |

## How it was generated

Written by hand by Claude (claude-opus-5-5, Claude Code) using the starter pack's
`generate-assignment-data` skill, on 2026-10-24, in about 30 minutes. No random generation,
so no random seed. Each request targets one check from the brief; wording varies (SKU,
catalog description, product type, number words, vague amounts, containers).

Expected results were written from the rules **before** running the application on the new
requests, and are never copied from its output. `scripts/check_expected.py` re-checks them
with code that is independent of the application (its own pricing with `Decimal` half-up
rounding, its own file parsing): every price and total, every request id against its input
file and order reference, agreement with the supplied `expected-seed-results.json`, and the
aggregate counts. Run it with `just check-data`.

## Coverage

| Check from the brief | Requests |
|---|---|
| Normal order, prices match a checked reference | R1, R5, R6 (bulk), R7 (two lines, bulk on one), R8 (by description) |
| Unknown product left unresolved, with a clarification | R2 |
| Ambiguous product | R3, R12 |
| Ambiguous quantity flagged, not guessed | R3 (boxes), R9 ("some"), R10 (packs) |
| Duplicate creates no second order | R4 (identical to R1) |
| Same order reference, different text | R13 (changes R5's order) |
| Model failure is visible, batch continues | R11 (simulated, labelled) |
| Unusable input is reported, batch continues | R14 (deliberately invalid: no `Order-Ref`) |
| Reviewer correction changes the proposal and reruns checks | C1 on R12's draft |

Deliberately invalid input: R14 only. R11 is a valid request whose model call fails on
purpose. No accidental data errors are known.

## Assumptions and open questions

- **A1 Packs.** `domain.md` rule 1 forbids inferring how many items a *box* holds. Packs (R10)
  are treated the same way: the quantity needs clarification.
- **A2 Vague amounts.** "some" (R9) is an ambiguous quantity under rule 3; no default is used.
- **A3 Same order, different text.** Rule 4 says requests with the same order reference are
  the same order, but not what to do when their content differs (R13). We don't merge or
  replace: no new draft is made and the existing draft is flagged for review.
- **A4 Correction reply.** C1's customer reply ("the 2 m cable") is fictional; there is no
  inbound reply channel.

These fixtures show the application handles each listed case; they are far too few to say
anything about real-world model accuracy.
