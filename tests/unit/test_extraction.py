import json

import pytest

from app.core.enums import ResponseSource
from app.models import Product
from app.services.extraction import (
    Extraction,
    ExtractionError,
    extract_order,
    render_system_prompt,
)
from tests.fakes import ScriptedProvider, answer, item, search

PRODUCTS = [
    Product(sku="CAB-1", name="USB-C cable 1 m", unit_cents=2000),
    Product(sku="CAB-2", name="USB-C cable 2 m", unit_cents=3000),
    Product(sku="HUB-1", name="USB hub", unit_cents=5000),
]


async def extract(provider: ScriptedProvider, text: str = "2 CAB-1", budget: int = 5) -> Extraction:
    return await extract_order(
        request_id="R1", text=text, products=PRODUCTS, provider=provider, search_budget=budget
    )


def test_prompt_describes_the_catalog_but_never_lists_rows() -> None:
    prompt = render_system_prompt(len(PRODUCTS), 5)

    assert "3 products" in prompt
    assert "`sku`" in prompt
    assert "CAB-1" not in prompt
    assert "2000" not in prompt


async def test_searches_are_answered_and_recorded() -> None:
    provider = ScriptedProvider({"R1": [search("CAB-1"), answer(item("2 CAB-1", "CAB-1", 2))]})

    extraction = await extract(provider)

    assert extraction.result.lines[0].sku == "CAB-1"
    assert [(s.query, [h.sku for h in s.results]) for s in extraction.searches] == [
        ("CAB-1", ["CAB-1"])
    ]
    assert [call["source"] for call in extraction.calls] == [ResponseSource.CACHED] * 2
    assert extraction.calls[0]["tool_results"] == [
        {"results": [{"sku": "CAB-1", "name": "USB-C cable 1 m"}]}
    ]


async def test_answer_is_forced_once_the_search_budget_is_used() -> None:
    provider = ScriptedProvider(
        {"R1": [search("cable"), answer(item("2 cables", None, 2, candidates=("CAB-1",)))]}
    )

    await extract(provider, budget=1)

    assert [call["tool_choice"] for call in provider.calls] == ["auto", "none"]


async def test_searches_beyond_the_budget_are_refused() -> None:
    provider = ScriptedProvider({"R1": [search("cable", "hub"), answer(item("2", None, 2))]})

    extraction = await extract(provider, budget=1)

    assert len(extraction.searches) == 1
    assert "error" in extraction.calls[0]["tool_results"][1]


async def test_invalid_search_arguments_are_reported_back_to_the_model() -> None:
    provider = ScriptedProvider({"R1": [search("   "), answer(item("2", None, 2))]})

    extraction = await extract(provider)

    assert extraction.searches == []
    assert "invalid arguments" in extraction.calls[0]["tool_results"][0]["error"]


async def test_invalid_output_is_an_extraction_error() -> None:
    bad = {"role": "assistant", "content": json.dumps({"lines": [{"sku": 1}]}), "tool_calls": None}

    with pytest.raises(ExtractionError, match="invalid model output") as caught:
        await extract(ScriptedProvider({"R1": [bad]}))

    assert len(caught.value.calls) == 1


async def test_provider_failure_keeps_its_label() -> None:
    with pytest.raises(ExtractionError) as caught:
        await extract(ScriptedProvider({}))

    assert caught.value.calls[0]["source"] == ResponseSource.CACHED
    assert "error" in caught.value.calls[0]


async def test_cache_keys_are_stable_across_runs() -> None:
    runs = [
        ScriptedProvider({"R1": [search("CAB-1"), answer(item("2 CAB-1", "CAB-1", 2))]})
        for _ in range(2)
    ]
    for provider in runs:
        await extract(provider)

    first, second = ([call["cache_key"] for call in provider.calls] for provider in runs)
    assert first == second
    assert first[0].startswith("R1.01.")
