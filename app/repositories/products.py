from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Product]:
        return list(await self.session.scalars(select(Product).order_by(Product.sku)))

    async def get_by_sku(self, sku: str) -> Product | None:
        return await self.session.scalar(select(Product).where(Product.sku == sku))

    async def upsert(self, *, sku: str, name: str, unit_cents: int) -> Product:
        product = await self.get_by_sku(sku)
        if product is None:
            product = Product(sku=sku, name=name, unit_cents=unit_cents)
            self.session.add(product)
        else:
            product.name = name
            product.unit_cents = unit_cents
        return product
