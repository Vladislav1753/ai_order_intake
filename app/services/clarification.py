"""Clarification email drafts, built from findings by template so nothing is invented."""

from collections import defaultdict

from app.core.enums import FindingCode
from app.schemas.draft import CheckedDraft, CheckedLine
from app.services.validation import CLARIFICATION_CODES


def clarification_text(order_ref: str, draft: CheckedDraft) -> str | None:
    """A message asking the customer for whatever blocks the order, or None if nothing does."""
    codes_by_line: defaultdict[int | None, list[FindingCode]] = defaultdict(list)
    for finding in draft.findings:
        if finding.code in CLARIFICATION_CODES:
            codes_by_line[finding.line].append(finding.code)
    if not codes_by_line:
        return None

    questions = []
    if None in codes_by_line:
        questions.append(
            "We couldn't find any products in your message. "
            "Could you list the SKUs or product names and how many of each you need?"
        )
    for line in draft.lines:
        if line.position in codes_by_line:
            asks = " ".join(_ask(code, line) for code in codes_by_line[line.position])
            questions.append(f'"{line.customer_text}": {asks}')

    bullets = "\n".join(f"- {question}" for question in questions)
    return (
        "Hello,\n\n"
        f"Thank you for your order {order_ref}. Before we can prepare it, "
        "could you help us with the following?\n\n"
        f"{bullets}\n\n"
        "Kind regards,\nOrder desk"
    )


def _ask(code: FindingCode, line: CheckedLine) -> str:
    match code:
        case FindingCode.UNKNOWN_PRODUCT:
            return (
                "we couldn't find this product in our catalog. "
                "Could you send the SKU or the full product name?"
            )
        case FindingCode.AMBIGUOUS_PRODUCT:
            options = " or ".join(f"{hit.sku} ({hit.name})" for hit in line.candidates)
            return f"this could be {options}. Which one do you need?"
        case FindingCode.NON_INDIVIDUAL_UNIT:
            return (
                f"we sell these as individual items and have no set {line.unit_label} size. "
                "How many individual items do you need?"
            )
        case _:
            return "How many individual items do you need?"
