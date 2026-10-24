"""Pydantic models to the provider's strict JSON-schema formats (the only schema source)."""

from typing import Any

from openai import pydantic_function_tool
from pydantic import BaseModel


def function_tool(model: type[BaseModel], *, name: str, description: str) -> dict[str, Any]:
    return dict(pydantic_function_tool(model, name=name, description=description))


def json_schema_format(model: type[BaseModel], *, name: str) -> dict[str, Any]:
    """`response_format` for a final answer that must validate as `model`."""
    schema = pydantic_function_tool(model, name=name)["function"].get("parameters")
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}
