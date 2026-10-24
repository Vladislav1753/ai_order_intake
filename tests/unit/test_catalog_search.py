import pytest

from app.cli import read_seed_file
from app.core.config import PROJECT_ROOT
from app.models import Product
from app.services.catalog import search_catalog, tokens

CATALOG = [
    Product(sku=item.sku, name=item.name, unit_cents=item.unit_cents)
    for item in read_seed_file(PROJECT_ROOT / "data" / "seed" / "seed.json").catalog
]


def skus(query: str) -> list[str]:
    return [product.sku for product in search_catalog(CATALOG, query)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("CAB-1", ["CAB-1"]),
        ("CAB-1 cables", ["CAB-1"]),
        ("usb-c cable 2 m", ["CAB-2"]),
        ("USB hub", ["HUB-1"]),
        ("the usual cable", ["CAB-1", "CAB-2"]),  # ambiguous: every tie is returned
        ("Moon adapter", []),  # unknown product
        ("", []),
    ],
)
def test_search_catalog(query: str, expected: list[str]) -> None:
    assert skus(query) == expected


def test_tokens_split_hyphenated_words_and_drop_plural_s() -> None:
    assert tokens("CAB-1 Cables") == {"cab-1", "cab", "1", "cable"}
