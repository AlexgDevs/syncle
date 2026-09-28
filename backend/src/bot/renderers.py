from src.modules.analytics import AnalysisReport

NO_DATA = "—"
PRICE_UNAVAILABLE = "недоступна"
DESCRIPTION_LIMIT = 600

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


def render_analysis_report(report: AnalysisReport) -> str:
    card = report.competitor
    description = (card.description or "").strip() or NO_DATA
    if len(description) > DESCRIPTION_LIMIT:
        description = description[:DESCRIPTION_LIMIT].rstrip() + "…"
    return ANALYSIS_REPORT.format(
        title=card.title or NO_DATA,
        brand=card.brand or NO_DATA,
        category=card.category or NO_DATA,
        price=str(card.price) if card.price is not None else PRICE_UNAVAILABLE,
        rating=card.rating if card.rating is not None else NO_DATA,
        feedbacks=(
            card.feedbacks_count if card.feedbacks_count is not None else NO_DATA
        ),
        description=description,
    )
