"""Parsing of LLM content-weakness output (issue #13).

Lives outside `service.py` because the golden-set harness
(`golden.py`) evaluates the same parser without needing the service.
"""

import json

_MAX_WEAKNESSES = 5


def _format_weakness(item: object) -> str | None:
    """Normalize one weakness: plain string or fact/evidence/how_to_beat object."""
    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, dict):
        parts = [
            str(item.get(field) or "").strip()
            for field in ("fact", "evidence", "how_to_beat")
        ]
        parts = [part for part in parts if part]
        if not parts:
            return None
        text = parts[0]
        for part in parts[1:]:
            separator = " " if text.endswith((".", "!", "?")) else ". "
            text += separator + part
        if not text.endswith((".", "!", "?")):
            text += "."
        return text
    return None


def parse_weaknesses(raw: str) -> list[str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data.get("content_weaknesses") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    formatted = [_format_weakness(item) for item in items]
    return [text for text in formatted if text][:_MAX_WEAKNESSES]
