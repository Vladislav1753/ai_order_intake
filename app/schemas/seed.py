from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class CatalogItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str
    name: str
    unit_cents: PositiveInt


class RequestIn(BaseModel):
    """One customer message, in the starter pack's request.template.json shape."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    order_ref: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1)


class SeedFile(BaseModel):
    catalog: list[CatalogItem]
    requests: list[RequestIn] = []
