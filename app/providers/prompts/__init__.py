"""Prompt templates. Bump PROMPT_VERSION whenever a template's meaning changes."""

from pathlib import Path

PROMPT_VERSION = "extract-v2"

EXTRACT_SYSTEM = (Path(__file__).parent / "extract_system.md").read_text(encoding="utf-8")
