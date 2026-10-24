"""Pricing rules from data/seed/domain.md. Integer cents only."""

from typing import NamedTuple

BULK_MIN_QUANTITY = 10
BULK_DISCOUNT_PERCENT = 10


class LinePrice(NamedTuple):
    unit_cents: int
    line_cents: int
    discount_cents: int
    total_cents: int


def bulk_discount_cents(quantity: int, line_cents: int) -> int:
    """10% off a line of at least 10 items, to the nearest cent with halves rounded up."""
    if quantity < BULK_MIN_QUANTITY:
        return 0
    return (line_cents * BULK_DISCOUNT_PERCENT + 50) // 100


def price_line(quantity: int, unit_cents: int) -> LinePrice:
    if quantity <= 0:
        raise ValueError(f"quantity must be positive, got {quantity}")
    line_cents = quantity * unit_cents
    discount_cents = bulk_discount_cents(quantity, line_cents)
    return LinePrice(unit_cents, line_cents, discount_cents, line_cents - discount_cents)
