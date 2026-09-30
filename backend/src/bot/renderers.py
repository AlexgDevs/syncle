from decimal import Decimal

from src.modules.analytics import AnalysisReport, CompetitorCard

NO_DATA = "—"
PRICE_UNAVAILABLE = "недоступна"
DESCRIPTION_LIMIT = 600
WEAKNESS_ITEM_LIMIT = 500
REPORT_LIMIT = 4000

ANALYSIS_REPORT = (
    "📊 Анализ карточки конкурента\n\n"
    "Заголовок: {title}\n"
    "Бренд: {brand}\n"
    "Категория: {category}\n"
    "Цена: {price}\n"
    "Рейтинг: {rating}\n"
    "Отзывов: {feedbacks}\n\n"
    "Описание:\n{description}"
)

COMPARISON_REPORT = (
    "📊 Сравнение карточек\n\n"
    "👤 Твоя карточка:\n{own}\n\n"
    "🏁 Конкурент:\n{rival}\n"
    "{missed}{weaknesses}"
)

CARD_BLOCK = (
    "Заголовок: {title}\n" "Цена: {price} · Рейтинг: {rating} · Отзывов: {feedbacks}"
)

MISSED_KEYS = "\n🔑 Упущенные SEO-ключи (есть у конкурента, нет у тебя):\n{keys}"

MISSED_KEYS_EMPTY = "\n🔑 Упущенные SEO-ключи: не найдены — уже покрыты.\n"

WEAKNESSES = "\n⚠️ Слабые места контента конкурента:\n{items}"


def _price(price: Decimal | None) -> str:
    return str(price) if price is not None else PRICE_UNAVAILABLE


def _clamp(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _card_line(card: CompetitorCard) -> str:
    return CARD_BLOCK.format(
        title=card.title or NO_DATA,
        price=_price(card.price),
        rating=card.rating if card.rating is not None else NO_DATA,
        feedbacks=(
            card.feedbacks_count if card.feedbacks_count is not None else NO_DATA
        ),
    )


def _render_single(report: AnalysisReport) -> str:
    card = report.competitor
    description = (card.description or "").strip() or NO_DATA
    if len(description) > DESCRIPTION_LIMIT:
        description = description[:DESCRIPTION_LIMIT].rstrip() + "…"
    return ANALYSIS_REPORT.format(
        title=card.title or NO_DATA,
        brand=card.brand or NO_DATA,
        category=card.category or NO_DATA,
        price=_price(card.price),
        rating=card.rating if card.rating is not None else NO_DATA,
        feedbacks=(
            card.feedbacks_count if card.feedbacks_count is not None else NO_DATA
        ),
        description=description,
    )


def _render_comparison(report: AnalysisReport) -> str:
    own = report.own_card
    if own is None:
        return _render_single(report)
    if report.missed_seo_keys:
        keys = "· " + " · ".join(report.missed_seo_keys)
        missed = MISSED_KEYS.format(keys=keys)
    else:
        missed = MISSED_KEYS_EMPTY
    if report.content_weaknesses:
        items = "\n".join(
            f"• {_clamp(item, WEAKNESS_ITEM_LIMIT)}"
            for item in report.content_weaknesses
        )
        weaknesses = WEAKNESSES.format(items=items)
    else:
        weaknesses = ""
    return COMPARISON_REPORT.format(
        own=_card_line(own),
        rival=_card_line(report.competitor),
        missed=missed,
        weaknesses=weaknesses,
    )


def render_analysis_report(report: AnalysisReport) -> str:
    if report.own_card is not None:
        text = _render_comparison(report)
    else:
        text = _render_single(report)
    return _clamp(text, REPORT_LIMIT)
