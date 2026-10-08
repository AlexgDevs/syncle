"""Tolerant JSON object extraction from LLM completions.

Every feature prompt demands "ONLY valid JSON" but models still wrap the
answer in Markdown fences or append prose, so one extractor is shared
instead of a copy per feature.
"""

import json
from typing import Any


def extract_json_object(raw: str) -> dict[str, Any] | None:
    """Return the JSON object embedded in ``raw``, or None when unusable.

    Tolerates code fences and surrounding prose; None means no JSON
    object, invalid JSON, or a non-object payload.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
