from decimal import Decimal

from src.modules.analytics import (
    AnalysisReport,
    CompetitorCard,
    NicheReport,
    PositioningInsight,
)

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
    "Оптимальная цена: {optimal}\n"
    "Рейтинг: {rating}\n"
    "Отзывов: {feedbacks}\n\n"
    "Описание:\n{description}"
)

COMPARISON_REPORT = (
    "📊 Сравнение карточек\n\n"
    "👤 Твоя карточка:\n{own}\n\n"
    "🏁 Конкурент:\n{rival}"
    "{optimal}\n{missed}{positioning}{weaknesses}"
)

CARD_BLOCK = (
    "Заголовок: {title}\n" "Цена: {price} · Рейтинг: {rating} · Отзывов: {feedbacks}"
)

MISSED_KEYS = "\n🔑 Упущенные SEO-ключи (есть у конкурента, нет у тебя):\n{keys}"

MISSED_KEYS_EMPTY = "\n🔑 Упущенные SEO-ключи: не найдены — уже покрыты.\n"

WEAKNESSES = "\n⚠️ Слабые места контента конкурента:\n{items}"

POSITIONING = "\n\n🎯 Позиционирование:\n{items}\n"

PRICE_AHEAD = "• Цена: выигрываешь — {own} ₽ против {rival} ₽"
PRICE_BEHIND = "• Цена: проигрываешь — {own} ₽ против {rival} ₽"
PRICE_EVEN = "• Цена: одинаковая — {own} ₽"
PRICE_UNKNOWN = "• Цена: данных нет — совет по цене не даётся"

KEYWORDS_AHEAD = "• Ключи: выигрываешь — {count}"
KEYWORDS_BEHIND = "• Ключи: проигрываешь — {count}"
KEYWORDS_EVEN = "• Ключи: полное совпадение — нет ни своих, ни упущенных"

RATING_AHEAD = "• Рейтинг: выигрываешь — {own} против {rival}"
RATING_BEHIND = "• Рейтинг: проигрываешь — {own} против {rival}"
RATING_EVEN = "• Рейтинг: равный — {own}"
RATING_UNKNOWN = "• Рейтинг: данных нет по одной из карточек"

OPTIMAL_PRICE = "\n💡 Оптимальная цена для нас: {optimal} ₽{note}"

OPTIMAL_OWN_LOWER = " — твоя цена уже ниже, обыгрывай контентом"

OPTIMAL_OWN_HIGHER = " — твоя цена выше на {delta} ₽"


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
        optimal=_price(report.optimal_price),
        rating=card.rating if card.rating is not None else NO_DATA,
        feedbacks=(
            card.feedbacks_count if card.feedbacks_count is not None else NO_DATA
        ),
        description=description,
    )


def _plural_ru(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _positioning_line(insight: PositioningInsight) -> str:
    own = insight.own_value or NO_DATA
    rival = insight.rival_value or NO_DATA
    if insight.axis == "price":
        if insight.stance == "unknown":
            return PRICE_UNKNOWN
        template = {"ahead": PRICE_AHEAD, "behind": PRICE_BEHIND}.get(
            insight.stance, PRICE_EVEN
        )
        return template.format(own=own, rival=rival)
    if insight.axis == "keywords":
        if insight.stance == "ahead":
            count = insight.exclusive_count or 0
            noun = _plural_ru(
                count, "эксклюзивный ключ", "эксклюзивных ключа", "эксклюзивных ключей"
            )
            return KEYWORDS_AHEAD.format(count=f"{count} {noun}")
        if insight.stance == "behind":
            count = insight.missed_count or 0
            noun = _plural_ru(
                count, "упущенный ключ", "упущенных ключа", "упущенных ключей"
            )
            return KEYWORDS_BEHIND.format(count=f"{count} {noun}")
        return KEYWORDS_EVEN
    if insight.stance == "unknown":
        return RATING_UNKNOWN
    template = {"ahead": RATING_AHEAD, "behind": RATING_BEHIND}.get(
        insight.stance, RATING_EVEN
    )
    return template.format(own=own, rival=rival)


def _positioning_block(report: AnalysisReport) -> str:
    if not report.positioning:
        return ""
    items = "\n".join(_positioning_line(insight) for insight in report.positioning)
    return POSITIONING.format(items=items)


def _optimal_block(report: AnalysisReport) -> str:
    optimal = report.optimal_price
    if optimal is None:
        return ""
    own = report.own_card
    note = ""
    if own is not None and own.price is not None:
        if own.price <= optimal:
            note = OPTIMAL_OWN_LOWER
        else:
            note = OPTIMAL_OWN_HIGHER.format(delta=own.price - optimal)
    return OPTIMAL_PRICE.format(optimal=optimal, note=note)


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
        optimal=_optimal_block(report),
        missed=missed,
        positioning=_positioning_block(report),
        weaknesses=weaknesses,
    )


def render_analysis_report(report: AnalysisReport) -> str:
    if report.own_card is not None:
        text = _render_comparison(report)
    else:
        text = _render_single(report)
    return _clamp(text, REPORT_LIMIT)


NICHE_REPORT = (
    "🔍 Глубокий скан ниши «{query}» · {mp}\n\n"
    "В выборке: {total} товаров\n"
    "💰 Цены: {prices} (покрытие {coverage}%)\n"
    "{price_bands}"
    "⭐ Средний рейтинг: {rating} (у {rating_count} товаров)\n"
    "💬 Отзывов: {feedbacks} всего, максимум у одного товара: {feedbacks_max}\n"
    "{feedback_bands}"
    "🏷 Топ брендов: {brands}\n"
    "🔑 Ключевые слова: {words}"
    "{insights}"
)

NICHE_PRICES = "от {low} до {high}, средняя {avg}"

NICHE_PRICES_NONE = "нет данных по ценам"

NICHE_PRICE_BAND = "   • {low}–{high}: {count} шт\n"

NICHE_PRICE_BAND_LAST = "   • от {low}: {count} шт\n"

NICHE_FEEDBACK_BAND = "   • отзывов {label}: {count} шт\n"

NICHE_INSIGHTS = "\n💡 Выводы:\n{items}"

NICHE_NO_INSIGHTS = "\n💡 Выводы: LLM временно недоступен — сводка выше."

NICHE_FILE_CAPTION = "📄 Полный отчёт по нише «{query}»"


def _niche_prices(report: NicheReport) -> str:
    stats = report.stats
    if stats.price_min is None or stats.price_max is None:
        return NICHE_PRICES_NONE
    return NICHE_PRICES.format(
        low=stats.price_min, high=stats.price_max, avg=stats.price_avg
    )


def _niche_price_bands(report: NicheReport) -> str:
    lines = []
    bands = report.stats.price_bands
    for index, band in enumerate(bands):
        if band.high is None or index == len(bands) - 1:
            lines.append(NICHE_PRICE_BAND_LAST.format(low=band.low, count=band.count))
        else:
            lines.append(
                NICHE_PRICE_BAND.format(low=band.low, high=band.high, count=band.count)
            )
    return "".join(lines)


def _niche_feedback_bands(report: NicheReport) -> str:
    lines = []
    for band in report.stats.feedback_bands:
        label = (
            "0"
            if band.high == 0
            else (f"{band.low}+" if band.high is None else f"{band.low}–{band.high}")
        )
        lines.append(NICHE_FEEDBACK_BAND.format(label=label, count=band.count))
    return "".join(lines)


def render_niche_report(report: NicheReport, limit: int | None = REPORT_LIMIT) -> str:
    """Renders the niche scan report; ``limit=None`` keeps the full text."""
    stats = report.stats
    mp_name = {"wb": "Wildberries", "ozon": "Ozon"}.get(
        report.marketplace, report.marketplace
    )
    brands = (
        " · ".join(f"{b.brand} ({b.count})" for b in stats.brand_mix)
        if stats.brand_mix
        else NO_DATA
    )
    words = (
        " · ".join(f"{w.word} ({w.count})" for w in stats.top_title_words)
        if stats.top_title_words
        else NO_DATA
    )
    if report.insights:
        items = "\n".join(f"• {item}" for item in report.insights)
        insights = NICHE_INSIGHTS.format(items=items)
    else:
        insights = NICHE_NO_INSIGHTS
    text = NICHE_REPORT.format(
        query=report.query,
        mp=mp_name,
        total=stats.total_items,
        prices=_niche_prices(report),
        coverage=round(stats.price_coverage * 100),
        price_bands=_niche_price_bands(report),
        rating=stats.rating_avg if stats.rating_avg is not None else NO_DATA,
        rating_count=stats.rating_count,
        feedbacks=stats.feedbacks_total,
        feedbacks_max=(
            stats.feedbacks_max if stats.feedbacks_max is not None else NO_DATA
        ),
        feedback_bands=_niche_feedback_bands(report),
        brands=brands,
        words=words,
        insights=insights,
    )
    if limit is None:
        return text
    return _clamp(text, limit)
