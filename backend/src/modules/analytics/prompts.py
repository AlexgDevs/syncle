"""Prompts for express comparison.

TODO(F15): move to a versioned prompt registry shared by all modules.
"""

from src.modules.analytics.schemas import CompetitorCard

COMPARISON_SYSTEM = (
    "Ты — аналитик карточек Wildberries для селлера. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и без Markdown."
)

_JSON_FORMAT = (
    'Формат ответа: {"content_weaknesses": ['
    '{"fact": "что описано слабо", '
    '"evidence": "конкретный факт из данных выше", '
    '"how_to_beat": "как нашему селлеру это обыграть"}]}'
)
_STRUCTURE_RULES = (
    "Каждый пункт — объект ровно из трёх полей: fact, evidence, how_to_beat. "
    "Все три поля — непустые фразы на русском языке; в каждом пункте до 2 предложений."
)
_MAX_DESCRIPTION = 3000
COMPARISON_TEMPERATURE = 0.4
COMPARISON_MAX_TOKENS = 800


def _card_block(card: CompetitorCard) -> str:
    description = (card.description or "").strip()
    if len(description) > _MAX_DESCRIPTION:
        description = description[:_MAX_DESCRIPTION].rstrip() + "…"
    price = str(card.price) if card.price is not None else "недоступна"
    return (
        f"Заголовок: {card.title or '—'}\n"
        f"Бренд: {card.brand or '—'}\n"
        f"Категория: {card.category or '—'}\n"
        f"Цена: {price}\n"
        f"Рейтинг: {card.rating if card.rating is not None else '—'}\n"
        f"Отзывов: {card.feedbacks_count if card.feedbacks_count is not None else '—'}\n"
        f"Описание: {description or '—'}"
    )


def build_comparison_prompt(
    own: CompetitorCard,
    rival: CompetitorCard,
    missed_keys: list[str],
) -> str:
    """Build the weaknesses prompt for one own/rival pair."""
    keys = ", ".join(missed_keys) if missed_keys else "не найдены"
    return (
        "Сравни две карточки товара Wildberries.\n\n"
        f"--- НАША КАРТОЧКА ---\n{_card_block(own)}\n\n"
        f"--- КАРТОЧКА КОНКУРЕНТА ---\n{_card_block(rival)}\n\n"
        f"Ключи SEO, которые есть у конкурента, но отсутствуют у нас: {keys}\n\n"
        "Назови до 5 слабых мест контента карточки КОНКУРЕНТА: что описано "
        "слабо, отсутствует или не убеждает покупателя — на что наш селлер "
        "может обыграть конкурента. Только по данным выше, без выдуманных "
        "цифр и фактов, на русском языке.\n"
        f"{_STRUCTURE_RULES}\n"
        f"{_JSON_FORMAT}"
    )
