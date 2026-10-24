import pytest
from pydantic import ValidationError

from app.schemas.review import MAX_QUANTITY, CorrectionField, LineCorrection


def correction(field: str, value: str | None) -> LineCorrection:
    return LineCorrection.model_validate({"line": 1, "field": field, "value": value})


@pytest.mark.parametrize(("value", "expected"), [("12", 12), ("007", 7), (" 3 ", 3), ("", None)])
def test_a_quantity_is_a_whole_number_of_items_or_empty(value: str, expected: int | None) -> None:
    assert correction("quantity", value).new_value == expected


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "2e3", "two", "٣", str(MAX_QUANTITY + 1)])
def test_anything_else_is_not_a_quantity(value: str) -> None:
    with pytest.raises(ValidationError, match="positive whole number"):
        correction("quantity", value)


def test_a_sku_is_kept_as_text_and_blank_clears_it() -> None:
    assert correction("sku", " CAB-2 ").new_value == "CAB-2"
    assert correction("sku", "").new_value is None
    assert correction("sku", "CAB-2").field is CorrectionField.SKU


@pytest.mark.parametrize(("line", "field"), [(0, "sku"), (1, "unit_cents"), (1, "status")])
def test_only_sku_and_quantity_of_an_existing_line_number_can_change(line: int, field: str) -> None:
    with pytest.raises(ValidationError):
        LineCorrection.model_validate({"line": line, "field": field, "value": "1"})
