"""Write results/report.md: expected vs observed for every input and the five minimum checks.

Processes all inputs on a fresh temporary database from the committed replays (no API key,
no network), processes them a second time, applies correction C1, then reads everything
back through a new engine, as a restarted app would. Expected values come from
data/expected/expected-results.json, never from the application.
Run: just report (uv run python -m scripts.results_report)
"""

import asyncio
import json
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.cli import process, read_seed_file, seed
from app.core.config import PROJECT_ROOT, Settings
from app.core.enums import RequestStatus
from app.db.migrations import run_alembic
from app.db.session import make_engine, make_sessionmaker
from app.models import DraftOrder, IncomingRequest
from app.repositories.drafts import DraftRepository
from app.repositories.requests import RequestRepository
from app.schemas.review import LineCorrection
from app.services.inbox import load_requests
from app.services.intake import IntakeResult
from app.services.review import ReviewService

EXPECTED: dict[str, Any] = json.loads(
    (PROJECT_ROOT / "data/expected/expected-results.json").read_text(encoding="utf-8")
)
CASES: dict[str, dict[str, Any]] = {case["id"]: case for case in EXPECTED["requests"]}
REPORT = PROJECT_ROOT / "results" / "report.md"

Requests = dict[str, IncomingRequest]
Drafts = dict[str, DraftOrder]


async def read_back(database_url: str) -> tuple[Requests, Drafts]:
    """Every request keyed by its case id (unusable files by source) and drafts by order."""
    engine = make_engine(database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            requests = await RequestRepository(session).list_all()
            drafts = await DraftRepository(session).list_all()
    finally:
        await engine.dispose()
    by_source = {case["source"]: case_id for case_id, case in CASES.items()}
    keyed = {
        (
            by_source[r.source_path or ""]
            if r.external_id.startswith("unusable-")
            else r.external_id
        ): r
        for r in requests
    }
    return keyed, {draft.order_ref: draft for draft in drafts}


async def apply_c1(database_url: str, draft_id: int) -> DraftOrder:
    """Apply C1 as the review screen does, then read the draft back through a new engine."""
    change = EXPECTED["corrections"][0]["change"]
    correction = LineCorrection.model_validate(
        {"line": change["line"], "field": change["field"], "value": change["to"]}
    )
    engine = make_engine(database_url)
    try:
        async with make_sessionmaker(engine)() as session:
            await ReviewService(session).correct(draft_id, correction)
    finally:
        await engine.dispose()
    engine = make_engine(database_url)  # the restart
    try:
        async with make_sessionmaker(engine)() as session:
            draft = await DraftRepository(session).get(draft_id)
    finally:
        await engine.dispose()
    assert draft is not None
    return draft


def lines_text(lines: Iterable[dict[str, Any]]) -> str:
    parts = []
    for line in lines:
        product = line.get("sku") or "/".join(line.get("candidates") or []) + "?"
        priced = f" = {line['total_cents']:,}" if line.get("total_cents") is not None else ""
        parts.append(f"{product} x{line.get('quantity') or '?'}{priced}")
    return "; ".join(parts)


def observed_lines(draft: DraftOrder) -> list[dict[str, Any]]:
    proposed = draft.proposal_json["lines"]
    return [
        {
            "sku": line.sku,
            "quantity": line.quantity,
            "unit": line.unit_label,
            "unit_cents": line.unit_cents,
            "line_cents": line.line_cents,
            "discount_cents": line.discount_cents,
            "total_cents": line.total_cents,
            "candidates": [hit["sku"] for hit in proposal["candidates"]],
        }
        for line, proposal in zip(draft.lines, proposed, strict=True)
    ]


def outcome_text(status: str, draft_status: str | None, lines: str, total: int | None) -> str:
    if draft_status is None:
        return f"{status}, no new draft"
    return f"{status} → {draft_status} · {lines} · total {total or 0:,}"


def expected_text(case: dict[str, Any]) -> str:
    text = outcome_text(
        case["request_status"],
        case.get("draft_status"),
        lines_text(case.get("lines", [])),
        case.get("total_cents"),
    )
    if "draft_status" not in case:
        return text
    return f"{text} · {', '.join(case['findings']) or 'no findings'}"


def observed_text(request: IncomingRequest | None, draft: DraftOrder | None) -> str:
    if request is None:
        return "not stored"
    own = draft is not None and draft.source_request_id == request.id
    if request.status is not RequestStatus.DRAFTED or not own or draft is None:
        return outcome_text(request.status.value, None, "", None)
    codes = ", ".join(finding["code"] for finding in draft.findings) or "no findings"
    text = outcome_text(
        request.status.value,
        draft.status.value,
        lines_text(observed_lines(draft)),
        draft.total_cents,
    )
    return f"{text} · {codes}"


def mismatches(case: dict[str, Any], request: IncomingRequest | None, draft: Drafts) -> list[str]:
    """Every expected field that the stored result doesn't match."""
    if request is None:
        return ["request not stored"]
    problems = []
    if request.status != case["request_status"]:
        problems.append(f"request {request.status}")
    sources = [call.get("source") for call in request.model_calls]
    if "model_call_source" in case and case["model_call_source"] not in sources:
        problems.append(f"model call sources {sources}")
    if "draft_status" not in case:
        own = draft.get(case["order_ref"])
        if own is not None and own.source_request_id == request.id:
            problems.append("created a draft")
        return problems
    found = draft.get(case["order_ref"])
    if found is None:
        return [*problems, "no draft"]
    if found.status != case["draft_status"]:
        problems.append(f"draft {found.status}")
    if [finding["code"] for finding in found.findings] != case["findings"]:
        problems.append("findings differ")
    if "total_cents" in case and found.total_cents != case["total_cents"]:
        problems.append(f"total {found.total_cents}")
    observed = observed_lines(found)
    if len(observed) != len(case["lines"]):
        return [*problems, f"{len(observed)} lines"]
    for number, (line, expected) in enumerate(zip(observed, case["lines"], strict=True), 1):
        problems += [
            f"line {number} {field}={line[field]}"
            for field, value in expected.items()
            if line[field] != value
        ]
    return problems


def sources_text(request: IncomingRequest | None) -> str:
    if request is None or not request.model_calls:
        return "none"
    counts = Counter(str(call.get("source")) for call in request.model_calls)
    return ", ".join(f"{source} x{count}" for source, count in counts.items())


def counts_text(counts: dict[str, int]) -> str:
    return ", ".join(f"{name} {count}" for name, count in sorted(counts.items()))


def verdict(ok: bool) -> str:
    return "✅ pass" if ok else "❌ FAIL"


def row(*cells: object) -> str:
    return "| " + " | ".join(str(cell).replace("|", "\\|") for cell in cells) + " |"


async def build() -> tuple[str, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite+aiosqlite:///{(Path(tmp) / 'report.db').as_posix()}"
        settings = Settings(_env_file=None, model_mode="replay", database_url=url)
        engine = make_engine(url)
        await run_alembic(engine, "upgrade", "head")
        await engine.dispose()
        await seed(settings, read_seed_file(settings.seed_dir / "seed.json").catalog)
        inputs = load_requests(settings.seed_dir / "seed.json", settings.inbox_dir)

        await process(settings, *inputs)
        requests, drafts = await read_back(url)
        rerun: list[IntakeResult] = await process(settings, *inputs)
        _, drafts_after_rerun = await read_back(url)
        c1 = EXPECTED["corrections"][0]
        corrected = await apply_c1(url, drafts[c1["order_ref"]].id)
        _, drafts_after_c1 = await read_back(url)

    lines: list[str] = []
    failures: list[str] = []
    problems = {
        case_id: mismatches(case, requests.get(case_id), drafts) for case_id, case in CASES.items()
    }

    # The five minimum checks.
    r2, r4 = drafts["O2"], requests["R4"]
    unknown_ok = (
        not problems["R2"]
        and r2.lines[0].sku is None
        and r2.clarification_text is not None
        and "Moon adapter" in r2.clarification_text
    )
    quantity_ok = not problems["R10"] and not problems["R9"]
    # Failed requests are retried on every run by design; only a new draft would be a new order.
    new_in_rerun = sum(
        1 for r in rerun if r.status is RequestStatus.DRAFTED and not r.already_processed
    )
    duplicate_ok = (
        not problems["R4"]
        and len(drafts) == EXPECTED["aggregates"]["drafts"]
        and len(drafts_after_rerun) == len(drafts)
        and new_in_rerun == 0
    )
    (history,) = corrected.corrections
    change = c1["change"]
    observed_c1 = [{k: line[k] for k in c1["lines_after"][0]} for line in observed_lines(corrected)]
    c1_ok = (
        observed_c1 == c1["lines_after"]
        and corrected.total_cents == c1["total_cents"]
        and corrected.status == c1["status_after"]
        and (history.field, history.old_value, history.new_value)
        == (change["field"], change["from"], change["to"])
        and (history.status_before, history.status_after)
        == (c1["status_before"], c1["status_after"])
    )
    clarification = next(
        (q[2:] for q in (r2.clarification_text or "").splitlines() if q.startswith("- ")), "none"
    )
    minimum = [
        (
            "Normal request becomes the expected draft, prices match the checked reference",
            "R7",
            expected_text(CASES["R7"]),
            observed_text(requests["R7"], drafts["O7"]),
            not problems["R7"],
        ),
        (
            "Unknown product left unresolved, with a useful clarification draft",
            "R2",
            expected_text(CASES["R2"]) + "; clarification asks for the product",
            f"{observed_text(requests['R2'], r2)}; clarification: {clarification}",
            unknown_ok,
        ),
        (
            "Ambiguous quantity flagged, not guessed",
            "R10, R9",
            f"{expected_text(CASES['R10'])}<br>{expected_text(CASES['R9'])}",
            f"{observed_text(requests['R10'], drafts['O10'])}<br>"
            f"{observed_text(requests['R9'], drafts['O9'])}",
            quantity_ok,
        ),
        (
            "Duplicate creates no second order and doesn't inflate the new-order count",
            "R4",
            f"duplicate of R1, no new draft; {EXPECTED['aggregates']['drafts']} new orders "
            "from 14 requests; processing everything again adds 0",
            f"{r4.status.value}, {sum(1 for d in drafts.values() if d.order_ref == 'O1')} draft "
            f"for O1; {len(drafts)} new orders; processing again: {new_in_rerun} new drafts, "
            f"{len(drafts_after_rerun)} drafts",
            duplicate_ok,
        ),
        (
            "Reviewer correction changes the saved draft, re-runs the checks, survives a restart",
            "C1 on R12",
            f"{c1['status_before']} → {c1['status_after']} · {lines_text(c1['lines_after'])} · "
            f"total {c1['total_cents']:,} · history {change['field']}: empty → {change['to']}",
            f"{history.status_before} → {corrected.status} · "
            f"{lines_text(observed_lines(corrected))} · total {corrected.total_cents:,} · history "
            f"{history.field}: {history.old_value or 'empty'} → {history.new_value} "
            "(read back after restart)",
            c1_ok,
        ),
    ]
    passed = sum(ok for *_, ok in minimum) + sum(not p for p in problems.values())
    total = len(minimum) + len(problems)

    lines += [
        "# Results: expected vs observed",
        "",
        "Generated by `just report` (`scripts/results_report.py`); do not edit by hand. It",
        "processes all 14 inputs on a fresh temporary database from the committed replays:",
        "saved real responses from gpt-4.1-mini, labelled `cached` (R11's failure is",
        "simulated and labelled `simulated-failure`). No API key or network is used. It then",
        "processes everything again, applies correction C1, and reads the result back through",
        "a new database engine, as a restarted app would.",
        "",
        "Expected values come from `data/expected/expected-results.json`, derived by hand from",
        "`data/seed/domain.md` and checked by `just check-data`, never from the application.",
        "`tests/acceptance/` asserts the same things on every commit. Amounts are in cents.",
        "",
        f"**{passed} of {total} checks pass.**",
        "",
        "## Minimum demonstration",
        "",
        row("#", "Check", "Case", "Expected", "Observed", "Result"),
        row("---", "---", "---", "---", "---", "---"),
    ]
    for number, (check, label, expected, observed, ok) in enumerate(minimum, 1):
        lines.append(row(number, check, label, expected, observed, verdict(ok)))
        if not ok:
            failures.append(f"Minimum check {number} ({label})")

    lines += [
        "",
        "## Every input",
        "",
        row("Request", "Expected", "Observed", "Model responses", "Result"),
        row("---", "---", "---", "---", "---"),
    ]
    for case_id, case in CASES.items():
        request = requests.get(case_id)
        result = verdict(not problems[case_id])
        if problems[case_id]:
            result += ": " + "; ".join(problems[case_id])
            failures.append(f"{case_id}: {'; '.join(problems[case_id])}")
        lines.append(
            row(
                case_id,
                expected_text(case),
                observed_text(request, drafts.get(case["order_ref"])),
                sources_text(request),
                result,
            )
        )

    aggregates = EXPECTED["aggregates"]
    observed_counts = [
        ("Requests", aggregates["requests"], len(requests)),
        (
            "Request outcomes",
            counts_text(aggregates["request_status"]),
            counts_text(Counter(r.status.value for r in requests.values())),
        ),
        ("New orders (drafts)", aggregates["drafts"], len(drafts)),
        (
            "Draft status after processing",
            counts_text(aggregates["draft_status_after_processing"]),
            counts_text(Counter(d.status.value for d in drafts.values())),
        ),
        ("New drafts when everything is processed again", 0, new_in_rerun),
        (
            "Draft status after correction C1",
            counts_text(aggregates["draft_status_after_corrections"]),
            counts_text(Counter(d.status.value for d in drafts_after_c1.values())),
        ),
    ]
    lines += ["", "## Counts", "", row("", "Expected", "Observed", "Result")]
    lines.append(row("---", "---", "---", "---"))
    for label, expected_count, observed_count in observed_counts:
        ok = str(expected_count) == str(observed_count)
        lines.append(row(label, expected_count, observed_count, verdict(ok)))
        if not ok:
            failures.append(f"Count: {label}")

    lines += ["", "## Failed checks", ""]
    lines += [f"- {failure}" for failure in failures] or ["None."]
    return "\n".join(lines) + "\n", not failures


def main() -> None:
    report, ok = asyncio.run(build())
    REPORT.write_text(report, encoding="utf-8", newline="\n")
    outcome = "all checks pass" if ok else "FAILURES, see the report"
    print(f"Wrote {REPORT.relative_to(PROJECT_ROOT).as_posix()}: {outcome}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
