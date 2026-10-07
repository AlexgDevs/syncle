"""Shared parser for fenced JSON payloads returned by the LLM.

Every feature prompt demands "ONLY valid JSON" but models still wrap the
answer in Markdown fences or append prose, so one tolerant decoder is
shared instead of a copy per feature.
"""

import json
from typing import Any


def parse_json_list(raw: str, key: str) -> list[Any] | None:
    """Return the payload list under ``key`` after stripping code fences.

    None means the payload is not usable (bad JSON, not an object, or the
    key is missing/not a list) — callers degrade to an empty result.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    items = data.get(key) if isinstance(data, dict) else None
    return items if isinstance(items, list) else None
