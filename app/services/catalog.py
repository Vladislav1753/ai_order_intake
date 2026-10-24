import re
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product
from app.repositories.products import ProductRepository
from app.schemas.seed import CatalogItem

# Words that never identify a product. Quantities are not here on purpose: "2 m" is part of a name.
_STOPWORDS = frozenset({"a", "an", "the", "of", "and", "or", "for", "please", "send", "some"})
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _normalize(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word  # "cables" -> "cable"


def tokens(text: str) -> set[str]:
    """Lower-cased words; hyphenated words also count by their parts ("CAB-1" -> cab-1, cab, 1)."""
    words: set[str] = set()
    for word in _WORD.findall(text.lower()):
        words.add(_normalize(word))
        if "-" in word:
            words.update(_normalize(part) for part in word.split("-"))
    return words - _STOPWORDS


def search_catalog(products: Sequence[Product], query: str, limit: int = 5) -> list[Product]:
    """Products sharing the most words with `query` (SKU or name); ties are all returned.

    Several results means the query is ambiguous; it is the caller's job to say so, not to pick.
    The catalog is small, so this scores in memory; a real one would use SQLite FTS5.
    """
    query_tokens = tokens(query)
    scored = [(len(query_tokens & tokens(f"{p.sku} {p.name}")), p) for p in products]
    best = max((score for score, _ in scored), default=0)
    if best == 0:
        return []
    return sorted((p for score, p in scored if score == best), key=lambda p: p.sku)[:limit]


async def load_catalog(session: AsyncSession, items: Sequence[CatalogItem]) -> int:
    """Insert or update every catalog item by SKU. Safe to run repeatedly."""
    products = ProductRepository(session)
    for item in items:
        await products.upsert(sku=item.sku, name=item.name, unit_cents=item.unit_cents)
    await session.commit()
    return len(items)
