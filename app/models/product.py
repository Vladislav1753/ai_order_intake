from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class Product(CreatedAtMixin, Base):
    """Catalog entry, loaded from data/seed/seed.json."""

    __tablename__ = "products"
    __table_args__ = (CheckConstraint("unit_cents > 0", name="unit_cents_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    unit_cents: Mapped[int] = mapped_column(Integer)
