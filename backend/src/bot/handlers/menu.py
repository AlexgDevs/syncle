from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.inline import back_menu, main_menu, submenu
from src.bot.texts import GREETING, MENU_TITLES, STUB_TEXT

router = Router(name="menu")

STUB_TITLES = {
    "unit_calc": "Быстрый расчёт",
    "weekly_report": "Отчёт WB/Ozon",
    "review_audit": "Аудит отзывов",
    "card_risks": "Риски карточки товара",
    "legal_audit": "Комплексный аудит бизнеса",
}


async def _show_menu(callback: CallbackQuery, state: FSMContext, name: str) -> None:
    await state.clear()
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    if name == "main":
        text, keyboard = GREETING, main_menu()
    elif name in MENU_TITLES:
        text, keyboard = MENU_TITLES[name], submenu(name)
    else:
        await callback.answer("Неизвестный раздел", show_alert=True)
        return
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("menu:"))
async def menu_navigation(callback: CallbackQuery, state: FSMContext) -> None:
    data = callback.data or ""
    await _show_menu(callback, state, data.removeprefix("menu:"))


@router.callback_query(F.data.startswith("stub:"))
async def menu_stub(callback: CallbackQuery) -> None:
    data = callback.data or ""
    title = STUB_TITLES.get(data.removeprefix("stub:"))
    if title is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await callback.message.edit_text(
        STUB_TEXT.format(title=title), reply_markup=back_menu()
    )
    await callback.answer()
