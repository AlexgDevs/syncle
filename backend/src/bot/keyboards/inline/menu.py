from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.texts import (
    BACK_TO_MENU,
    BTN_COPY_DESCRIPTION,
    BTN_COPY_TITLE,
    BTN_SKIP,
    SEO_MENU_LABEL,
)
from src.modules.analytics.enums import MARKETPLACE_TITLES
from src.modules.content import SeoText

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
        [("🏷 Аудит и авто-теги отзывов", "stub:review_audit")],
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
    builder.row(InlineKeyboardButton(text=BACK_TO_MENU, callback_data="menu:main"))
    return builder.as_markup()
