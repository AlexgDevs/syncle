"""Prompts for review analysis (issue #29).

TODO(F15): move to a versioned prompt registry shared by all modules.
"""

from src.modules.analytics.schemas import Review
from src.modules.reviews.schemas import (
    MAX_FINDINGS,
    MAX_POINT_LEN,
    MAX_POINTS_PER_TAG,
    ReviewAnalysisRequest,
    ReviewSource,
    Tone,
)

REVIEWS_SYSTEM = (
    "Ты — аналитик отзывов маркетплейсов для селлера. "
    "Пиши только на русском языке. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и без Markdown."
)

TONE_RULES: dict[Tone, str] = {
    Tone.NEUTRAL: "Тон: нейтральный — сухая аналитика, без эмоций и оценок.",
    Tone.SOFT: "Тон: мягкий — деликатные формулировки, без давления на селлера.",
    Tone.HARSH: "Тон: жёсткий — прямые и резкие формулировки, без смягчений.",
}

_GROUNDING_RULES = (
    "Правила содержания:\n"
    "- называй ТОЛЬКО проблемы, которые реально указаны в отзывах или "
    "описании выше — не выдумывай жалобы, которых нет в данных;\n"
    f"- не больше {MAX_FINDINGS} разных тегов;\n"
    f"- на каждый тег до {MAX_POINTS_PER_TAG} пунктов, каждый пункт до "
    f"{MAX_POINT_LEN} символов;\n"
    "- пункты — конкретные факты из отзывов, на русском языке."
)

_TAG_RULES = (
    "Правила тегов:\n"
    "- каждый тег начинается с #, слова пишутся через подчёркивание, "
    "без пробелов и других разделителей;\n"
    "- только русские буквы, латиница и цифры, примеры: "
    "#Проблема_Упаковка, #Доставка_Сроки, #Брак_Товара;\n"
    "- одинаковые проблемы объединяй под одним тегом, не дублируй теги."
)

_JSON_FORMAT = (
    'Формат ответа: {"findings": [{"tag": "#Проблема_Упаковка", '
    '"points": ["конкретная проблема из отзывов", "ещё проблема"]}]}'
)

REVIEWS_TEMPERATURE = 0.4
REVIEWS_MAX_TOKENS = 900

_MAX_REVIEW_LEN = 400

_SOURCE_TITLES = {
    "own": "--- НАШ ТОВАР ---",
    "rival": "--- ТОВАР КОНКУРЕНТА ---",
}


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    return text[:limit].rstrip() + "…" if len(text) > limit else text


def _review_block(index: int, review: Review) -> str:
    parts = []
    if review.rating is not None:
        parts.append(f"Оценка: {review.rating}")
    if review.pros:
        parts.append(f"Плюсы: {_cut(review.pros, _MAX_REVIEW_LEN)}")
    if review.cons:
        parts.append(f"Минусы: {_cut(review.cons, _MAX_REVIEW_LEN)}")
    if review.text:
        parts.append(f"Текст: {_cut(review.text, _MAX_REVIEW_LEN)}")
    body = "; ".join(parts) or "без текста"
    return f"{index}. {body}"


def _source_block(source: ReviewSource) -> str:
    lines = [_SOURCE_TITLES[source.role]]
    if source.description:
        lines.append(f"Описание: {_cut(source.description, _MAX_REVIEW_LEN)}")
    if source.reviews:
        lines.append(f"Отзывов: {len(source.reviews)}")
        lines.extend(
            _review_block(index, review)
            for index, review in enumerate(source.reviews, start=1)
        )
    return "\n".join(lines)


def build_reviews_prompt(request: ReviewAnalysisRequest) -> str:
    """Build the findings prompt for one request (typed vars, #29)."""
    blocks = "\n\n".join(_source_block(source) for source in request.sources)
    return (
        "Найди проблемы товара по отзывам и описанию, сгруппируй их по "
        "тегам.\n\n"
        f"{blocks}\n\n"
        f"{TONE_RULES[request.tone]}\n\n"
        f"{_GROUNDING_RULES}\n"
        f"{_TAG_RULES}\n"
        f"{_JSON_FORMAT}"
    )


def build_reviews_repair_prompt(
    request: ReviewAnalysisRequest, errors: list[str]
) -> str:
    """Ask the model to fix its invalid answer (#30)."""
    listed = "\n".join(f"- {error}" for error in errors)
    return (
        "Твой предыдущий ответ не прошёл валидацию:\n"
        f"{listed}\n\n"
        "Отправь исправленный ответ. Условия те же:\n\n"
        f"{build_reviews_prompt(request)}"
    )
