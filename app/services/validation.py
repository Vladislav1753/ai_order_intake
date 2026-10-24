"""Code-side checks: what the model proposed is only kept if the catalog lookups back it up."""

from collections.abc import Mapping, Sequence

from app.core.enums import DraftStatus, FindingCode
from app.schemas.draft import CheckedDraft, CheckedLine, Finding, LineInput
from app.schemas.extraction import CatalogHit, CatalogSearch, ExtractedLine, QuantityUnit
from app.services.catalog import tokens
from app.services.pricing import price_line

# Findings the customer has to answer. Anything else is for the reviewer only.
CLARIFICATION_CODES = frozenset(
    {
        FindingCode.UNKNOWN_PRODUCT,
        FindingCode.AMBIGUOUS_PRODUCT,
        FindingCode.AMBIGUOUS_QUANTITY,
        FindingCode.NON_INDIVIDUAL_UNIT,
    }
)


def resolve_model_lines(
    lines: Sequence[ExtractedLine], searches: Sequence[CatalogSearch]
) -> tuple[list[LineInput], list[Finding]]:
    """Turn the model's lines into check input, trusting only what the searches returned.

    Each line cites the search that matched it (`matched_query`). Its SKU is kept only if
    that search returned exactly that one product and the query shares a word with the
    customer's text for the line, so a match found for one item can't be reused for another.
    A SKU picked among tied results goes back to ambiguous. Containers never become items.
    """
    returned = {hit.sku: hit for search in searches for hit in search.results}
    resolved: list[LineInput] = []
    findings: list[Finding] = []
    for position, line in enumerate(lines, start=1):
        sku = line.sku
        candidates = [returned[s] for s in dict.fromkeys(line.candidate_skus) if s in returned]
        if sku is not None:
            cited = _cited_search(line.matched_query, searches)
            cited_skus = [hit.sku for hit in cited.results] if cited else []
            grounded = cited is not None and _shares_a_word(cited.query, line.customer_text)
            if cited_skus == [sku] and grounded:
                candidates = [returned[sku]]
            else:
                problem = _unverified_reason(sku, line, cited, returned)
                if problem:
                    findings.append(
                        Finding(code=FindingCode.UNVERIFIED_SKU, line=position, message=problem)
                    )
                elif cited:  # the cited search returned several products: still ambiguous
                    candidates = _merge(candidates, cited.results)
                sku = None
        counts_items = line.unit is QuantityUnit.ITEM and (line.quantity or 0) > 0
        resolved.append(
            LineInput(
                customer_text=line.customer_text,
                matched_query=line.matched_query,
                sku=sku,
                quantity=line.quantity if counts_items else None,
                unit_label=line.unit.value if line.unit else None,
                candidates=candidates,
            )
        )
    return resolved, findings


def check_lines(
    lines: Sequence[LineInput], catalog: Mapping[str, int], extra: Sequence[Finding] = ()
) -> CheckedDraft:
    """Check and price every line. `catalog` maps SKU to unit price in cents."""
    findings = list(extra)
    if not lines:
        findings.append(
            Finding(
                code=FindingCode.UNKNOWN_PRODUCT, line=None, message="No product in the request."
            )
        )
    checked = []
    for position, line in enumerate(lines, start=1):
        findings.extend(_product_findings(position, line, catalog))
        findings.extend(_quantity_findings(position, line))
        checked.append(_priced(position, line, catalog))
    priced = [line for line in checked if line.total_cents is not None]
    return CheckedDraft(
        lines=checked,
        findings=findings,
        status=status_for(findings),
        subtotal_cents=sum(line.line_cents or 0 for line in priced),
        discount_cents=sum(line.discount_cents or 0 for line in priced),
        total_cents=sum(line.total_cents or 0 for line in priced),
    )


def status_for(findings: Sequence[Finding]) -> DraftStatus:
    codes = {finding.code for finding in findings}
    if codes & CLARIFICATION_CODES:
        return DraftStatus.NEEDS_CLARIFICATION
    if codes:
        return DraftStatus.NEEDS_REVIEW
    return DraftStatus.READY_FOR_REVIEW


def _product_findings(position: int, line: LineInput, catalog: Mapping[str, int]) -> list[Finding]:
    text = line.customer_text
    if line.sku is None and line.candidates:
        skus = ", ".join(hit.sku for hit in line.candidates)
        code, message = FindingCode.AMBIGUOUS_PRODUCT, f'"{text}" could be any of: {skus}.'
    elif line.sku is None:
        code, message = FindingCode.UNKNOWN_PRODUCT, f'No catalog product matches "{text}".'
    elif line.sku not in catalog:
        code, message = FindingCode.UNKNOWN_PRODUCT, f"{line.sku} is not in the catalog."
    else:
        return []
    return [Finding(code=code, line=position, message=message)]


def _quantity_findings(position: int, line: LineInput) -> list[Finding]:
    if line.quantity is not None and line.quantity > 0:
        return []
    if line.quantity is None and line.unit_label not in (None, QuantityUnit.ITEM):
        code = FindingCode.NON_INDIVIDUAL_UNIT
        message = f'"{line.customer_text}" is counted per {line.unit_label}; sizes are unknown.'
    else:
        code = FindingCode.AMBIGUOUS_QUANTITY
        message = f'No positive number of individual items in "{line.customer_text}".'
    return [Finding(code=code, line=position, message=message)]


def _priced(position: int, line: LineInput, catalog: Mapping[str, int]) -> CheckedLine:
    checked = CheckedLine(position=position, **line.model_dump())
    unit_cents = catalog.get(line.sku) if line.sku else None
    if unit_cents is not None and line.quantity is not None and line.quantity > 0:
        price = price_line(line.quantity, unit_cents)
        checked = checked.model_copy(update=price._asdict())
    return checked


def _cited_search(query: str | None, searches: Sequence[CatalogSearch]) -> CatalogSearch | None:
    wanted = (query or "").strip().casefold()
    return next((s for s in reversed(searches) if s.query.casefold() == wanted), None)


def _shares_a_word(query: str, customer_text: str) -> bool:
    """Digits don't count: the "1" in "CAB-1" says nothing about "1 box of cables"."""
    return any(not word.isdigit() for word in tokens(query) & tokens(customer_text))


def _unverified_reason(
    sku: str,
    line: ExtractedLine,
    cited: CatalogSearch | None,
    returned: Mapping[str, CatalogHit],
) -> str | None:
    """Why a proposed SKU has no support, or None if it is merely one of several matches."""
    if sku not in returned:
        return f"The model proposed {sku}, which no catalog search returned."
    if cited is None:
        return f"The model proposed {sku} but cited a search it never ran: {line.matched_query!r}."
    if sku not in (hit.sku for hit in cited.results):
        return f"The model proposed {sku}, but its search {cited.query!r} did not return it."
    if not _shares_a_word(cited.query, line.customer_text):
        return (
            f"The model proposed {sku} from search {cited.query!r}, which shares no words "
            f"with {line.customer_text!r}."
        )
    return None


def _merge(*groups: Sequence[CatalogHit]) -> list[CatalogHit]:
    return list(dict.fromkeys(hit for group in groups for hit in group))
