# Five reference cases

Checked by a person against `data/seed/domain.md`, independently of the application.
Catalog: CAB-1 USB-C cable 1 m 2,000 · CAB-2 USB-C cable 2 m 3,000 · HUB-1 USB hub 5,000
(cents per item). Bulk rule: a line of 10 or more items gets 10% off that line, rounded to
the nearest cent with halves up.

| # | Check (brief) | Input | Expected | Rule |
|---|---|---|---|---|
| 1 | Normal request, prices match | R7 `inbox/r07-cables-and-hub.txt`: "We need 10 CAB-1 cables and one USB hub" | Ready for review. CAB-1 × 10 = 20,000, discount 2,000, line 18,000. HUB-1 × 1 = 5,000, no discount. Subtotal 25,000, discount 2,000, **total 23,000** | 2, 3 |
| 2 | Unknown product left unresolved | R2 seed: "Please send one Moon adapter." | Needs clarification, product unresolved (no SKU), **not** mapped to another item, clarification asks for the product. No total | 3 |
| 3 | Ambiguous quantity flagged | R10 `inbox/r10-cable-packs.txt`: "Send 2 packs of CAB-1" | Needs clarification: product CAB-1, quantity left empty (pack size unknown), clarification asks for individual items. No total | 1, 3 |
| 4 | Duplicate creates no new order | R4 seed, identical to R1 (order O1) | Outcome duplicate; still one draft for O1 (total 4,000); not counted as a new order. Reprocessing R1 or R4 changes nothing | 4 |
| 5 | Reviewer correction | C1: R12 "Please send 10 USB-C cables" is ambiguous (CAB-1 or CAB-2); reviewer sets CAB-2 | Before: needs clarification. After: ready for review, CAB-2 × 10 = 30,000, discount 3,000, **total 27,000**; the correction (field, old, new, statuses) is saved and still shown after a restart | 2, 3 |

Hand arithmetic for the priced cases:

- Case 1: 10 × 2,000 = 20,000; 10% = 2,000.0 → 2,000; 20,000 − 2,000 = 18,000. 1 × 5,000 = 5,000.
  18,000 + 5,000 = 23,000.
- Case 4: 2 × 2,000 = 4,000 (the supplied seed expectation).
- Case 5: 10 × 3,000 = 30,000; 10% = 3,000.0 → 3,000; 30,000 − 3,000 = 27,000.

Verified by hand: [X] name Vladyslav Baklanov date 24.10.2026
