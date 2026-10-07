from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.inline import back_menu, main_menu, submenu
from src.bot.texts import (
    GREETING,
    MENU_TITLES,
    STUB_TEXT,
    STUB_TITLES,
    UNKNOWN_SECTION,
)
from src.bot.utils import safe_edit

router = Router(name="menu")


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
        await callback.answer(UNKNOWN_SECTION, show_alert=True)
        return
    await safe_edit(callback.message, text, keyboard)
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
    await safe_edit(callback.message, STUB_TEXT.format(title=title), back_menu())
    await callback.answer()
