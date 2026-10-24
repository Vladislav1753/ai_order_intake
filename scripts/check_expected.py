"""Check data/expected/expected-results.json against the inputs and the domain rules.

Independent of the application on purpose: prices are recomputed here with Decimal
half-up rounding (not app/services/pricing.py), and inbox files are parsed with a few lines
of code here (not app/services/inbox.py). Run: uv run python scripts/check_expected.py
"""

import json
import sys
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "data/seed/seed.json").read_text(encoding="utf-8"))
SEED_RESULTS = json.loads((ROOT / "data/seed/expected-seed-results.json").read_text("utf-8"))
EXPECTED = json.loads((ROOT / "data/expected/expected-results.json").read_text("utf-8"))
PRICES = {item["sku"]: item["unit_cents"] for item in SEED["catalog"]}

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def inputs() -> dict[str, tuple[str, str | None]]:
    """Request id -> (source file, order_ref) for every input file."""
    found = {r["id"]: ("data/seed/seed.json", r["order_ref"]) for r in SEED["requests"]}
    for path in sorted((ROOT / "data/inbox").iterdir()):
        if path.name.startswith("."):  # .gitkeep
            continue
        source = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            data = json.loads(text)
            found[data["id"]] = (source, data.get("order_ref"))
            continue
        headers = dict(
            (key.strip().lower(), value.strip())
            for key, _, value in (line.partition(":") for line in text.split("\n\n")[0].split("\n"))
        )
        found[headers["request-id"]] = (source, headers.get("order-ref"))
    return found


def price(sku: str, quantity: int) -> dict[str, int]:
    line = quantity * PRICES[sku]
    discount = 0
    if quantity >= 10:  # domain.md 2: 10% off the line, nearest cent, halves up
        discount = int((Decimal(line) / 10).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return {
        "unit_cents": PRICES[sku],
        "line_cents": line,
        "discount_cents": discount,
        "total_cents": line - discount,
    }


def check_priced(label: str, lines: list[dict[str, Any]], case: dict[str, Any]) -> None:
    priced = [line for line in lines if line.get("sku") and line.get("quantity")]
    for number, line in enumerate(lines, start=1):
        check(line.get("sku") is None or line["sku"] in PRICES, f"{label} line {number}: bad SKU")
        if line in priced:
            for field, value in price(line["sku"], line["quantity"]).items():
                check(line.get(field) == value, f"{label} line {number}: {field} != {value}")
    sums = {
        "subtotal_cents": sum(p["line_cents"] for p in priced),
        "discount_cents": sum(p["discount_cents"] for p in priced),
        "total_cents": sum(p["total_cents"] for p in priced),
    }
    for field, value in sums.items():
        check(case.get(field, value) == value, f"{label}: {field} != {value}")


def main() -> None:
    files = inputs()
    cases = {case["id"]: case for case in EXPECTED["requests"]}
    check(set(cases) == set(files), f"ids differ: {sorted(set(cases) ^ set(files))}")
    for request_id, case in cases.items():
        source, order_ref = files.get(request_id, ("?", None))
        check(case["source"] == source, f"{request_id}: source is {source}")
        check(case["order_ref"] == order_ref, f"{request_id}: order_ref is {order_ref}")
        check_priced(request_id, case.get("lines", []), case)
        if case["request_status"] == "duplicate":
            original = cases[case["same_order_as"]]
            check(original["order_ref"] == case["order_ref"], f"{request_id}: not the same order")

    for seed in SEED_RESULTS:  # the supplied expectations must still hold
        case = cases[seed["id"]]
        if seed["outcome"] == "draft":
            line = case["lines"][0]
            check(
                (line["sku"], line["quantity"], case["total_cents"])
                == (seed["sku"], seed["quantity"], seed["total_cents"]),
                f"{seed['id']}: differs from expected-seed-results.json",
            )
        elif seed["outcome"] == "needs-clarification":
            check(case["draft_status"] == "needs_clarification", f"{seed['id']}: not clarify")
        elif seed["outcome"] == "duplicate":
            check(case["request_status"] == "duplicate", f"{seed['id']}: not a duplicate")
            check(case["new_drafts"] == seed["new_drafts"], f"{seed['id']}: new drafts")

    statuses = {
        case["order_ref"]: case["draft_status"]
        for case in cases.values()
        if case["request_status"] == "drafted"
    }
    for correction in EXPECTED["corrections"]:
        check_priced(correction["id"], correction["lines_after"], correction)
        check(
            statuses[correction["order_ref"]] == correction["status_before"],
            f"{correction['id']}: status_before",
        )
    after = dict(statuses)
    after.update({c["order_ref"]: c["status_after"] for c in EXPECTED["corrections"]})

    totals = EXPECTED["aggregates"]
    check(totals["requests"] == len(cases), "aggregate requests")
    check(
        totals["request_status"] == dict(Counter(c["request_status"] for c in cases.values())),
        "aggregate request_status",
    )
    check(totals["drafts"] == len(statuses), "aggregate drafts")
    check(
        totals["draft_status_after_processing"] == dict(Counter(statuses.values())),
        "aggregate draft_status_after_processing",
    )
    check(
        totals["draft_status_after_corrections"] == dict(Counter(after.values())),
        "aggregate draft_status_after_corrections",
    )

    if errors:
        print("\n".join(f"FAIL {error}" for error in errors))
        sys.exit(1)
    print(f"OK: {len(cases)} requests, {len(EXPECTED['corrections'])} correction, aggregates match")


if __name__ == "__main__":
    main()
