"""What the model may send: the search tool's arguments and the final extraction.

The JSON schemas sent to the provider are generated from these models, so the prompt never
describes them by hand. Fields have no defaults and extra keys are forbidden, which keeps the
schemas valid for strict structured output.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuantityUnit(StrEnum):
    ITEM = "item"
    BOX = "box"
    PACK = "pack"
    OTHER = "other"


class SearchCatalogArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="Words to look for in the SKU or product name.")

    @field_validator("query")
    @classmethod
    def _query_is_short_text(cls, query: str) -> str:
        query = query.strip()
        if not 1 <= len(query) <= 100:
            raise ValueError("query must be 1-100 characters")
        return query


class CatalogHit(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str
    name: str


class CatalogSearch(BaseModel):
    """One `search_catalog` call made during extraction and what it returned."""

    query: str
    results: list[CatalogHit]


class ExtractedLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_text: str = Field(description="The customer's words for this item, with quantity.")
    matched_query: str | None = Field(
        description="The exact query of the search whose only result is sku; null if sku is."
    )
    sku: str | None = Field(
        description="Only a SKU that a search returned as its single result; otherwise null."
    )
    candidate_skus: list[str] = Field(
        description="If sku is null: SKUs returned by searches that could be this item."
    )
    quantity: int | None = Field(description="The number the customer gave; null if none.")
    unit: QuantityUnit | None = Field(
        description="What quantity counts: item for individual items, or the container used."
    )


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[ExtractedLine]
