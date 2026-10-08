"""Prompts for SEO text generation (issue #23).

TODO(F15): move to a versioned prompt registry shared by all modules.
"""

from src.modules.analytics.enums import MARKETPLACE_TITLES
from src.modules.content.schemas import SEO_LIMITS, SeoLimits, SeoRequest

SEO_SYSTEM = (
    "Ты — SEO-копирайтер карточек товаров для маркетплейсов. "
    "Пиши только на русском языке. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и без Markdown."
)

_JSON_FORMAT = (
    'Формат ответа: {"title": "название товара", '
    '"description": "описание товара", '
    '"bullets": ["преимущество 1", "преимущество 2"], '
    '"keywords": ["ключевое слово 1", "ключевое слово 2"]}'
)

_RULES = (
    "Правила:\n"
    "- все поля на русском языке, без Markdown и эмодзи;\n"
    "- title — цепляющее название, не дословно повторяй описание;\n"
    "- description — 3-6 предложений: состав, назначение, выгоды, кому подойдёт;\n"
    "- bullets — конкретные преимущества, по одному на пункт;\n"
    "- keywords — релевантные фразы, по которым товар ищут покупатели."
)

SEO_TEMPERATURE = 0.6
SEO_MAX_TOKENS = 900

# Long seller descriptions are truncated for the prompt; the schema keeps
# the full text.
_MAX_PROMPT_DESCRIPTION = 2000


def _limits_block(limits: SeoLimits) -> str:
    return (
        f"- title: до {limits.title} символов\n"
        f"- description: до {limits.description} символов\n"
        f"- bullets: до {limits.bullets} пунктов, каждый до "
        f"{limits.bullet_len} символов\n"
        f"- keywords: до {limits.keywords} штук, каждое до "
        f"{limits.keyword_len} символов"
    )


def _item_list(items: list[str]) -> str:
    joined = ", ".join(item.strip() for item in items if item.strip())
    return joined or "—"


def _request_block(request: SeoRequest) -> str:
    description = request.description.strip()
    if len(description) > _MAX_PROMPT_DESCRIPTION:
        description = description[:_MAX_PROMPT_DESCRIPTION].rstrip() + "…"
    lines = [f"Описание селлера: {description}"]
    if request.advantages:
        lines.append(f"Отметить преимущества: {_item_list(request.advantages)}")
    if request.keywords:
        lines.append(f"Целевые ключевые слова: {_item_list(request.keywords)}")
    if request.name:
        lines.append(f"Название (по фото): {request.name.strip()}")
    if request.category:
        lines.append(f"Категория (по фото): {request.category.strip()}")
    if request.brand:
        lines.append(f"Бренд (по фото): {request.brand.strip()}")
    if request.key_features:
        lines.append(
            f"Особенности товара (по фото): {_item_list(request.key_features)}"
        )
    return "\n".join(lines)


def build_seo_prompt(request: SeoRequest) -> str:
    """Build the generation prompt for one request (typed vars, #23)."""
    limits = SEO_LIMITS[request.marketplace]
    mp_name = MARKETPLACE_TITLES[request.marketplace]
    return (
        f"Составь SEO-текст для карточки товара на {mp_name}.\n\n"
        f"--- ТОВАР ---\n{_request_block(request)}\n\n"
        f"--- ЛИМИТЫ {mp_name.upper()} ---\n{_limits_block(limits)}\n\n"
        f"{_RULES}\n"
        f"{_JSON_FORMAT}"
    )


def build_seo_repair_prompt(request: SeoRequest, errors: list[str]) -> str:
    """Ask the model to fix its invalid answer (#25)."""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "Твой предыдущий ответ не прошёл валидацию:\n"
        f"{listed}\n\n"
        "Отправь исправленный ответ. Условия те же:\n\n"
        f"{build_seo_prompt(request)}"
    )
