from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.texts import (
    BACK_TO_MENU,
    BTN_ANALYZE,
    BTN_COPY_DESCRIPTION,
    BTN_COPY_TITLE,
    BTN_INFOGRAPHICS,
    BTN_PAGE_NEXT,
    BTN_PAGE_PREV,
    BTN_SKIP,
    BTN_STYLE_BRIGHT_SALE,
    BTN_STYLE_MINIMALISM,
    BTN_STYLE_PREMIUM,
    BTN_TONE_HARSH,
    BTN_TONE_NEUTRAL,
    BTN_TONE_SOFT,
    SEO_MENU_LABEL,
)
from src.modules.analytics.enums import MARKETPLACE_TITLES
from src.modules.analytics.schemas import Review
from src.modules.content import SeoText
from src.modules.reviews import ReviewReport

MAIN_ROWS = [
    [("📊 Аналитика ниши", "menu:niche")],
    [("💰 Финансы и юнит-экономика", "menu:finance")],
    [("⭐ Репутация и отзывы", "menu:reputation")],
    [("⚖️ Юридический сканер", "menu:legal")],
]

MENU_ROWS = {
    "niche": [
        [("⚡ Экспресс-анализ конкурента", "scene:express")],
        [("🔍 Глубокий скан ниши", "scene:deep_scan")],
        [(SEO_MENU_LABEL, "scene:seo")],
    ],
    "finance": [
        [("🧮 Быстрый расчёт", "stub:unit_calc")],
        [("📁 Отчёт WB/Ozon (Excel/CSV)", "stub:weekly_report")],
    ],
    "reputation": [
        [("🏷 Аудит и авто-теги отзывов", "scene:reviews")],
    ],
    "legal": [
        [("🛡 Риски карточки товара", "stub:card_risks")],
        [("📋 Комплексный аудит бизнеса", "stub:legal_audit")],
    ],
}


def _build(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.row(
            *[InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        )
    return builder.as_markup()


def main_menu() -> InlineKeyboardMarkup:
    return _build(MAIN_ROWS)


def submenu(name: str) -> InlineKeyboardMarkup:
    rows = MENU_ROWS[name] + [[(BACK_TO_MENU, "menu:main")]]
    return _build(rows)


def back_menu() -> InlineKeyboardMarkup:
    return _build([[(BACK_TO_MENU, "menu:main")]])


def express_setup() -> InlineKeyboardMarkup:
    return _build([[(BTN_SKIP, "scene:express:skip")], [(BACK_TO_MENU, "menu:main")]])


def deep_scan_mp() -> InlineKeyboardMarkup:
    return _build(
        [
            [
                (MARKETPLACE_TITLES["wb"], "scene:deep_scan:mp:wb"),
                (MARKETPLACE_TITLES["ozon"], "scene:deep_scan:mp:ozon"),
            ],
            [(BACK_TO_MENU, "menu:main")],
        ]
    )


def deep_scan_own_setup() -> InlineKeyboardMarkup:
    return _build([[(BTN_SKIP, "scene:deep_scan:skip")], [(BACK_TO_MENU, "menu:main")]])


def seo_mp() -> InlineKeyboardMarkup:
    return _build(
        [
            [
                (MARKETPLACE_TITLES["wb"], "scene:seo:mp:wb"),
                (MARKETPLACE_TITLES["ozon"], "scene:seo:mp:ozon"),
            ],
            [(BACK_TO_MENU, "menu:main")],
        ]
    )


def seo_keywords_setup() -> InlineKeyboardMarkup:
    return _build([[(BTN_SKIP, "scene:seo:skip")], [(BACK_TO_MENU, "menu:main")]])


COPY_TEXT_LIMIT = 256  # Telegram CopyTextButton.text: 1-256 characters


def seo_result_keyboard(text: SeoText) -> InlineKeyboardMarkup:
    """Result keyboard: copy title/description via Telegram copy buttons (#26).

    Telegram caps ``copy_text`` at 256 characters, so a button is built
    only for fields that fit; longer descriptions stay in the report
    message for manual copying.
    """
    builder = InlineKeyboardBuilder()
    copy_buttons = [
        InlineKeyboardButton(
            text=label,
            copy_text=CopyTextButton(text=value),
        )
        for label, value in (
            (BTN_COPY_TITLE, text.title),
            (BTN_COPY_DESCRIPTION, text.description),
        )
        if 0 < len(value) <= COPY_TEXT_LIMIT
    ]
    if copy_buttons:
        builder.row(*copy_buttons)
    builder.row(
        InlineKeyboardButton(text=BTN_INFOGRAPHICS, callback_data="scene:infographics")
    )
    builder.row(InlineKeyboardButton(text=BACK_TO_MENU, callback_data="menu:main"))
    return builder.as_markup()


def infographic_variants() -> InlineKeyboardMarkup:
    """Style picker for the infographics scene (issue #62)."""
    return _build(
        [
            [
                (BTN_STYLE_MINIMALISM, "scene:infographics:variant:minimalism"),
                (BTN_STYLE_PREMIUM, "scene:infographics:variant:premium"),
                (BTN_STYLE_BRIGHT_SALE, "scene:infographics:variant:bright_sale"),
            ],
            [(BACK_TO_MENU, "menu:main")],
        ]
    )


def infographic_photo_setup() -> InlineKeyboardMarkup:
    """Skip button while collecting customer photos (M7-v5)."""
    return _build(
        [[(BTN_SKIP, "scene:infographics:skip_photo")], [(BACK_TO_MENU, "menu:main")]]
    )


def reviews_rival_setup() -> InlineKeyboardMarkup:
    return _build([[(BTN_SKIP, "scene:reviews:skip")], [(BACK_TO_MENU, "menu:main")]])


def reviews_tone() -> InlineKeyboardMarkup:
    return _build(
        [
            [
                (BTN_TONE_NEUTRAL, "scene:reviews:tone:neutral"),
                (BTN_TONE_SOFT, "scene:reviews:tone:soft"),
                (BTN_TONE_HARSH, "scene:reviews:tone:harsh"),
            ],
            [(BACK_TO_MENU, "menu:main")],
        ]
    )


SELECTION_PAGE_SIZE = 10  # keeps serialized markup well under Telegram's ~10 KB cap


def reviews_selection(
    entries: list[tuple[str, Review]], selected: set[str], page: int = 0
) -> InlineKeyboardMarkup:
    """Paginated toggle list: checkbox per review, analyze, menu (#31).

    Callback data is ``scene:reviews:toggle:<role>:<id>``; role prefixing
    keeps keys unique when own and rival review ids collide. Telegram
    rejects keyboards over ~10 KB serialized / 100 buttons, so only one
    page of reviews is rendered at a time.
    """
    pages = max(1, -(-len(entries) // SELECTION_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    builder = InlineKeyboardBuilder()
    for key, review in entries[page * SELECTION_PAGE_SIZE :][:SELECTION_PAGE_SIZE]:
        source = review.text or review.pros or review.cons or "без текста"
        one_line = " ".join(source.split())
        excerpt = one_line[:45] + ("…" if len(one_line) > 45 else "")
        marker = "☑" if key in selected else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {excerpt}",
                callback_data=f"scene:reviews:toggle:{key}",
            )
        )
    if pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text=BTN_PAGE_PREV,
                    callback_data=f"scene:reviews:page:{page - 1}",
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{pages}", callback_data="scene:reviews:noop"
            )
        )
        if page < pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text=BTN_PAGE_NEXT,
                    callback_data=f"scene:reviews:page:{page + 1}",
                )
            )
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(
            text=BTN_ANALYZE.format(count=len(selected)),
            callback_data="scene:reviews:analyze",
        )
    )
    builder.row(InlineKeyboardButton(text=BACK_TO_MENU, callback_data="menu:main"))
    return builder.as_markup()


def reviews_result_keyboard(report: ReviewReport) -> InlineKeyboardMarkup:
    """Copy buttons, one per finding group (#31).

    Service clamps guarantee each group's points fit Telegram's 256-char
    copy limit (3 x 80 + separators <= 242).
    """
    builder = InlineKeyboardBuilder()
    for finding in report.findings:
        builder.row(
            InlineKeyboardButton(
                text=f"📋 {finding.tag}",
                copy_text=CopyTextButton(text="\n".join(finding.points)),
            )
        )
    builder.row(InlineKeyboardButton(text=BACK_TO_MENU, callback_data="menu:main"))
    return builder.as_markup()
