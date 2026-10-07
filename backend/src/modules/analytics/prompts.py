"""Prompts for express comparison.

TODO(F15): move to a versioned prompt registry shared by all modules.
"""

from src.modules.analytics.enums import MARKETPLACE_TITLES
from src.modules.analytics.schemas import CompetitorCard, NicheStats

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


NICHE_SYSTEM = (
    "Ты — аналитик маркетплейсов для селлера. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и без Markdown."
)
_NICHE_JSON_FORMAT = 'Формат ответа: {"insights": ["вывод 1", "вывод 2"]}'
_NICHE_RULES = (
    "Назови до 6 выводов о нише: ценовой сегмент и разброс цен, "
    "конкуренция по брендам и отзывам, заметные ключевые слова в заголовках. "
    "Если выше дана НАША КАРТОЧКА — добавь точки её улучшения относительно "
    "ниши. Каждый вывод — одна фраза на русском языке; обязательно цитируй "
    "конкретные числа из данных выше (цены, доли, количество отзывов). "
    "Только по данным выше, без выдуманных фактов."
)
NICHE_TEMPERATURE = 0.4
NICHE_MAX_TOKENS = 700


def build_niche_prompt(
    query: str,
    marketplace: str,
    stats: NicheStats,
    own: CompetitorCard | None = None,
) -> str:
    """Builds the niche insights prompt (issue #42) from aggregated stats."""
    mp_name = MARKETPLACE_TITLES.get(marketplace, marketplace)
    if stats.price_min is not None and stats.price_max is not None:
        prices = (
            f"от {stats.price_min} до {stats.price_max}, " f"средняя {stats.price_avg}"
        )
    else:
        prices = "недоступны"
    brands = (
        ", ".join(f"{b.brand} ({b.count})" for b in stats.brand_mix)
        if stats.brand_mix
        else "не найдены"
    )
    words = (
        ", ".join(f"{w.word} ({w.count})" for w in stats.top_title_words)
        if stats.top_title_words
        else "не найдены"
    )
    rating = str(stats.rating_avg) if stats.rating_avg is not None else "—"
    own_block = f"--- НАША КАРТОЧКА ---\n{_card_block(own)}\n\n" if own else ""
    return (
        "Оцни нишу товара по данным поисковой выдачи маркетплейса.\n\n"
        f"{own_block}"
        f"Поисковый запрос: {query}\n"
        f"Маркетплейс: {mp_name}\n"
        f"Товаров в выборке: {stats.total_items}\n"
        f"Цены: {prices} (есть у {stats.price_coverage:.0%} товаров)\n"
        f"Средний рейтинг: {rating} (у {stats.rating_count} товаров)\n"
        f"Отзывов всего: {stats.feedbacks_total} (максимум у одного товара: "
        f"{stats.feedbacks_max})\n"
        f"Бренды: {brands}\n"
        f"Ключевые слова в заголовках: {words}\n\n"
        f"{_NICHE_RULES}\n"
        f"{_NICHE_JSON_FORMAT}"
    )
