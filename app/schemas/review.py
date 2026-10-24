"""Reviewer input: one edit of one draft line."""

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# An input sanity bound so the price still fits in a SQLite integer, not a business rule.
MAX_QUANTITY = 999_999_999


class CorrectionField(StrEnum):
    SKU = "sku"
    QUANTITY = "quantity"


class LineCorrection(BaseModel):
    """An empty value clears the field, which puts the line back to unresolved."""

    model_config = ConfigDict(str_strip_whitespace=True)

    line: int = Field(ge=1)
    field: CorrectionField
    value: str | None = Field(default=None, max_length=64)

    @field_validator("value")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _quantity_is_a_count(self) -> "LineCorrection":
        if self.field is CorrectionField.QUANTITY and not _is_count(self.value):
            raise ValueError("quantity must be a positive whole number of individual items")
        return self

    @property
    def new_value(self) -> str | int | None:
        if self.field is CorrectionField.QUANTITY and self.value is not None:
            return int(self.value)
        return self.value


def _is_count(value: str | None) -> bool:
    """Empty (clear the quantity) or a whole number from 1 up, digits only."""
    return value is None or (
        re.fullmatch(r"[0-9]+", value) is not None and 0 < int(value) <= MAX_QUANTITY
    )
