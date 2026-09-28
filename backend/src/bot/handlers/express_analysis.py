from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.inline import back_menu
from src.bot.renderers import render_analysis_report
from src.bot.texts import (
    ANALYSIS_LOADING,
    CARD_NOT_FOUND,
    EXPRESS_PROMPT,
    INVALID_INPUT,
    MEDIA_HINT,
    PARSE_FAILED,
    UNSUPPORTED_MARKETPLACE,
)
from src.bot.utils import is_valid_card_input
from src.modules.analytics import get_analytics_service
from src.modules.analytics.errors import (
    CardNotFoundError,
    CardParseError,
    UnsupportedMarketplaceError,
)

router = Router(name="express_analysis")


class ExpressAnalysis(StatesGroup):
    waiting_input = State()


@router.callback_query(F.data == "scene:express")
async def start_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(ExpressAnalysis.waiting_input)
    await callback.message.edit_text(EXPRESS_PROMPT, reply_markup=back_menu())
    await callback.answer()


@router.message(ExpressAnalysis.waiting_input, F.text)
async def handle_input(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not is_valid_card_input(value):
        await message.answer(INVALID_INPUT)
        return
    status = await message.answer(ANALYSIS_LOADING)
    try:
        report = await get_analytics_service().analyze_card(value)
    except UnsupportedMarketplaceError as exc:
        await status.edit_text(
            UNSUPPORTED_MARKETPLACE.format(name=exc.marketplace.title())
        )
        return
    except CardNotFoundError:
        await status.edit_text(CARD_NOT_FOUND)
        return
    except CardParseError:
        await status.edit_text(PARSE_FAILED)
        return
    await state.clear()
    await status.edit_text(render_analysis_report(report), reply_markup=back_menu())


@router.message(ExpressAnalysis.waiting_input)
async def handle_media(message: Message) -> None:
    await message.answer(MEDIA_HINT)
