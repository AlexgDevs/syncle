"""Vision helper: product attributes from photos (issue #27).

One vision call turns downloaded photo bytes plus a short seller hint
into structured attributes that merge into the SEO request. Failures
raise domain errors; the bot catches them and degrades to text-only.
"""

import json
import logging

from pydantic import ValidationError

from src.core.llm import LLMProvider
from src.modules.content.errors import SeoGenerationError
from src.modules.content.schemas import MAX_KEY_FEATURES, SeoAttributes

logger = logging.getLogger(__name__)

VISION_SYSTEM = (
    "Ты распознаёшь товары по фотографиям для карточек маркетплейсов. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и без Markdown."
)

_VISION_JSON_FORMAT = (
    'Формат ответа: {"name": "название товара", '
    '"category": "категория товара", '
    '"brand": "бренд или null", '
    '"key_features": ["особенность 1", "особенность 2"]}'
)

_VISION_RULES = (
    "Правила:\n"
    "- определи название, категорию и бренд строго по фотографиям;\n"
    "- бренд не выдумывай, если его не видно — верни null;\n"
    "- key_features — до 3 конкретных особенностей, видимых на фото;\n"
    "- используй подсказку селлера, но не противоречь изображению."
)

VISION_TEMPERATURE = 0.2
VISION_MAX_TOKENS = 300


def build_vision_prompt(hint: str) -> str:
    """Build the attributes prompt for one photo set (+ seller hint)."""
    seller_hint = hint.strip() or "—"
    return (
        "Определи товар по фотографиям для карточки маркетплейса.\n\n"
        f"Подсказка селлера: {seller_hint}\n\n"
        f"{_VISION_RULES}\n"
        f"{_VISION_JSON_FORMAT}"
    )


def _extract_json(raw: str) -> dict[str, object] | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def describe_product(
    llm: LLMProvider,
    images: list[bytes],
    hint: str,
) -> SeoAttributes:
    """Return product attributes recognized from photos (#27).

    Raises:
        SeoGenerationError: vision output failed validation.
        LLMError: provider failure (timeout, rate limit, unavailable).
    """
    raw = await llm.complete(
        build_vision_prompt(hint),
        system=VISION_SYSTEM,
        temperature=VISION_TEMPERATURE,
        max_tokens=VISION_MAX_TOKENS,
        images=images,
    )
    data = _extract_json(raw)
    if data is None:
        raise SeoGenerationError("Vision output is not a JSON object")
    try:
        attributes = SeoAttributes.model_validate(data)
    except ValidationError as exc:
        raise SeoGenerationError(f"Vision output failed validation: {exc}") from exc
    features = [f.strip() for f in attributes.key_features if f.strip()]
    return attributes.model_copy(update={"key_features": features[:MAX_KEY_FEATURES]})
