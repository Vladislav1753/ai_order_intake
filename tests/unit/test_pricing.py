import pytest

from app.services.pricing import LinePrice, price_line


@pytest.mark.parametrize(
    ("quantity", "unit_cents", "expected"),
    [
        # domain.md worked example
        (2, 2000, LinePrice(2000, 4000, 0, 4000)),
        (10, 2000, LinePrice(2000, 20000, 2000, 18000)),
        # just below the bulk threshold: no discount
        (9, 3000, LinePrice(3000, 27000, 0, 27000)),
        # 10% of 55 is 5.5 cents: halves round up
        (11, 5, LinePrice(5, 55, 6, 49)),
        # 10% of 54 is 5.4 cents: rounds down
        (18, 3, LinePrice(3, 54, 5, 49)),
    ],
)
def test_price_line(quantity: int, unit_cents: int, expected: LinePrice) -> None:
    assert price_line(quantity, unit_cents) == expected


def test_price_line_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValueError, match="quantity"):
        price_line(0, 2000)
