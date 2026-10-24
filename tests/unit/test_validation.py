from app.core.enums import DraftStatus, FindingCode
from app.schemas.draft import Finding, LineInput
from app.schemas.extraction import CatalogHit, CatalogSearch, ExtractedLine, QuantityUnit
from app.services.clarification import clarification_text
from app.services.validation import check_lines, resolve_model_lines

CATALOG = {"CAB-1": 2000, "CAB-2": 3000, "HUB-1": 5000}
CAB_1 = CatalogHit(sku="CAB-1", name="USB-C cable 1 m")
CAB_2 = CatalogHit(sku="CAB-2", name="USB-C cable 2 m")


def line(
    sku: str | None,
    quantity: int | None = 2,
    unit: QuantityUnit | None = QuantityUnit.ITEM,
    candidates: list[str] | None = None,
    text: str = "2 CAB-1 cables",
    query: str | None = None,
) -> ExtractedLine:
    """A model line citing `query` (by default the SKU itself) as the search that matched it."""
    return ExtractedLine(
        customer_text=text,
        matched_query=query or sku,
        sku=sku,
        candidate_skus=candidates or [],
        quantity=quantity,
        unit=unit,
    )


def search(query: str, *hits: CatalogHit) -> CatalogSearch:
    return CatalogSearch(query=query, results=list(hits))


def codes(findings: list[Finding]) -> list[FindingCode]:
    return [finding.code for finding in findings]


def test_sku_its_cited_search_returned_alone_is_kept() -> None:
    lines, findings = resolve_model_lines([line("CAB-1")], [search("CAB-1", CAB_1)])

    assert findings == []
    assert lines[0].sku == "CAB-1"
    assert lines[0].candidates == [CAB_1]
    assert lines[0].matched_query == "CAB-1"


def test_cited_query_is_matched_ignoring_case() -> None:
    lines, _ = resolve_model_lines([line("CAB-1", query="cab-1")], [search("CAB-1", CAB_1)])

    assert lines[0].sku == "CAB-1"


def test_sku_picked_among_tied_results_is_left_unresolved() -> None:
    lines, findings = resolve_model_lines(
        [line("CAB-1", text="2 cables", query="cable")], [search("cable", CAB_1, CAB_2)]
    )

    assert findings == []  # ambiguous, which check_lines reports; not unverified
    assert lines[0].sku is None
    assert lines[0].candidates == [CAB_1, CAB_2]


def test_a_match_for_one_item_is_not_reused_for_another() -> None:
    lines, findings = resolve_model_lines(
        [line("CAB-1"), line("CAB-1", quantity=3, text="3 of the usual cable")],
        [search("CAB-1", CAB_1), search("usual cable", CAB_1, CAB_2)],
    )

    assert [resolved.sku for resolved in lines] == ["CAB-1", None]
    assert [(f.code, f.line) for f in findings] == [(FindingCode.UNVERIFIED_SKU, 2)]
    assert "shares no words" in findings[0].message


def test_digits_alone_do_not_tie_a_search_to_an_item() -> None:
    lines, findings = resolve_model_lines(
        [line("CAB-1", quantity=1, text="1 Moon adapter")], [search("CAB-1", CAB_1)]
    )

    assert lines[0].sku is None
    assert codes(findings) == [FindingCode.UNVERIFIED_SKU]


def test_sku_no_search_returned_is_rejected() -> None:
    lines, findings = resolve_model_lines([line("CAB-9")], [search("CAB-1", CAB_1)])

    assert lines[0].sku is None
    assert codes(findings) == [FindingCode.UNVERIFIED_SKU]
    assert "no catalog search returned" in findings[0].message


def test_citing_a_search_that_never_ran_is_rejected() -> None:
    lines, findings = resolve_model_lines(
        [line("CAB-1", query="CAB-1 cable")], [search("CAB-1", CAB_1)]
    )

    assert lines[0].sku is None
    assert "never ran" in findings[0].message


def test_citing_a_search_that_did_not_return_the_sku_is_rejected() -> None:
    lines, findings = resolve_model_lines(
        [line("CAB-2", text="2 cables 2 m", query="cable 2 m")],
        [search("cable 2 m", CAB_2), search("cable 1 m", CAB_1)],
    )
    assert lines[0].sku == "CAB-2"

    lines, findings = resolve_model_lines(
        [line("CAB-1", text="2 cables 2 m", query="cable 2 m")],
        [search("cable 2 m", CAB_2), search("cable 1 m", CAB_1)],
    )
    assert lines[0].sku is None
    assert "did not return it" in findings[0].message


def test_candidates_are_kept_only_if_a_search_returned_them() -> None:
    lines, _ = resolve_model_lines(
        [line(None, candidates=["CAB-1", "CAB-2", "HUB-9"])],
        [search("cable", CAB_1, CAB_2)],
    )

    assert lines[0].candidates == [CAB_1, CAB_2]


def test_boxes_are_never_converted_to_items() -> None:
    lines, _ = resolve_model_lines([line("CAB-1", unit=QuantityUnit.BOX)], [search("CAB-1", CAB_1)])

    assert lines[0].quantity is None
    assert lines[0].unit_label == "box"


def test_normal_order_is_priced_and_ready() -> None:
    draft = check_lines(
        [LineInput(customer_text="2 CAB-1", sku="CAB-1", quantity=2, unit_label="item")], CATALOG
    )

    assert draft.status is DraftStatus.READY_FOR_REVIEW
    assert draft.findings == []
    assert (draft.subtotal_cents, draft.discount_cents, draft.total_cents) == (4000, 0, 4000)


def test_bulk_line_gets_the_discount() -> None:
    draft = check_lines(
        [LineInput(customer_text="10 CAB-1", sku="CAB-1", quantity=10, unit_label="item")],
        CATALOG,
    )

    assert (draft.subtotal_cents, draft.discount_cents, draft.total_cents) == (20000, 2000, 18000)


def test_unknown_product_needs_clarification() -> None:
    draft = check_lines(
        [LineInput(customer_text="one Moon adapter", sku=None, quantity=1, unit_label="item")],
        CATALOG,
    )

    assert draft.status is DraftStatus.NEEDS_CLARIFICATION
    assert codes(draft.findings) == [FindingCode.UNKNOWN_PRODUCT]
    assert draft.lines[0].total_cents is None
    assert draft.total_cents == 0


def test_ambiguous_product_and_box_quantity_are_both_flagged() -> None:
    draft = check_lines(
        [
            LineInput(
                customer_text="two boxes of the usual cable",
                sku=None,
                quantity=None,
                unit_label="box",
                candidates=[CAB_1, CAB_2],
            )
        ],
        CATALOG,
    )

    assert draft.status is DraftStatus.NEEDS_CLARIFICATION
    assert codes(draft.findings) == [
        FindingCode.AMBIGUOUS_PRODUCT,
        FindingCode.NON_INDIVIDUAL_UNIT,
    ]


def test_missing_or_non_positive_quantity_is_ambiguous() -> None:
    draft = check_lines(
        [
            LineInput(customer_text="some CAB-1", sku="CAB-1", quantity=None, unit_label=None),
            LineInput(customer_text="0 CAB-2", sku="CAB-2", quantity=0, unit_label="item"),
        ],
        CATALOG,
    )

    assert codes(draft.findings) == [FindingCode.AMBIGUOUS_QUANTITY] * 2


def test_sku_outside_the_catalog_is_unknown() -> None:
    draft = check_lines(
        [LineInput(customer_text="2 CAB-7", sku="CAB-7", quantity=2, unit_label="item")], CATALOG
    )

    assert codes(draft.findings) == [FindingCode.UNKNOWN_PRODUCT]


def test_request_with_no_lines_needs_clarification() -> None:
    draft = check_lines([], CATALOG)

    assert draft.status is DraftStatus.NEEDS_CLARIFICATION
    assert draft.findings[0].line is None


def test_conflict_alone_needs_review() -> None:
    conflict = Finding(code=FindingCode.CONFLICTING_REQUEST, line=None, message="R9 differs")
    draft = check_lines(
        [LineInput(customer_text="2 CAB-1", sku="CAB-1", quantity=2, unit_label="item")],
        CATALOG,
        extra=[conflict],
    )

    assert draft.status is DraftStatus.NEEDS_REVIEW


def test_clarification_names_the_candidates_and_asks_for_items() -> None:
    draft = check_lines(
        [
            LineInput(
                customer_text="two boxes of the usual cable",
                sku=None,
                quantity=None,
                unit_label="box",
                candidates=[CAB_1, CAB_2],
            )
        ],
        CATALOG,
    )

    text = clarification_text("O3", draft)

    assert text is not None
    assert "CAB-1 (USB-C cable 1 m) or CAB-2 (USB-C cable 2 m)" in text
    assert "individual" in text


def test_ready_draft_has_no_clarification() -> None:
    draft = check_lines(
        [LineInput(customer_text="2 CAB-1", sku="CAB-1", quantity=2, unit_label="item")], CATALOG
    )

    assert clarification_text("O1", draft) is None
