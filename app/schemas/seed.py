from pydantic import BaseModel, ConfigDict, PositiveInt


class CatalogItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str
    name: str
    unit_cents: PositiveInt


class RequestIn(BaseModel):
    """One customer message, in the starter pack's request.template.json shape."""

    model_config = ConfigDict(frozen=True)

    id: str
    order_ref: str
    text: str


class SeedFile(BaseModel):
    catalog: list[CatalogItem]
    requests: list[RequestIn] = []
