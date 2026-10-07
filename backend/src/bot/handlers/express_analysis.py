from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.common import (
    launch_job_or_inline,
    register_media_hint,
    require_state,
    result_sink,
)
from src.bot.keyboards.inline import back_menu, express_setup
from src.bot.renderers import render_analysis_report
from src.bot.texts import (
    ANALYSIS_LOADING,
    EXPRESS_OWN_PROMPT,
    EXPRESS_RIVAL_PROMPT,
    INVALID_INPUT,
)
from src.bot.utils import is_valid_card_input, safe_edit
from src.modules.analytics import get_analytics_service
from src.modules.analytics.jobs import ANALYSIS_JOB_TYPE

router = Router(name="express_analysis")


class ExpressAnalysis(StatesGroup):
    waiting_own = State()
    waiting_rival = State()


@router.callback_query(F.data == "scene:express")
async def start_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(ExpressAnalysis.waiting_own)
    await safe_edit(callback.message, EXPRESS_OWN_PROMPT, express_setup())
    await callback.answer()


@router.callback_query(F.data == "scene:express:skip")
async def skip_own(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, ExpressAnalysis.waiting_own, callback):
        return
    await state.update_data(own=None)
    await state.set_state(ExpressAnalysis.waiting_rival)
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await safe_edit(callback.message, EXPRESS_RIVAL_PROMPT, back_menu())
    await callback.answer()


@router.message(ExpressAnalysis.waiting_own, F.text)
async def handle_own(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not is_valid_card_input(value):
        await message.answer(INVALID_INPUT)
        return
    await state.update_data(own=value)
    await state.set_state(ExpressAnalysis.waiting_rival)
    await message.answer(EXPRESS_RIVAL_PROMPT, reply_markup=back_menu())


@router.message(ExpressAnalysis.waiting_rival, F.text)
async def handle_rival(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not is_valid_card_input(value):
        await message.answer(INVALID_INPUT)
        return
    own = (await state.get_data()).get("own")
    own_source = own if isinstance(own, str) else None
    status = await message.answer(ANALYSIS_LOADING)
    if await launch_job_or_inline(
        state,
        ANALYSIS_JOB_TYPE,
        {
            "own": own_source,
            "rival": value,
            "chat_id": message.chat.id,
            "status_message_id": status.message_id,
        },
    ):
        return
    report = await get_analytics_service().compare_cards(own_source, value)
    await state.clear()
    await result_sink(message).deliver(
        message.chat.id,
        render_analysis_report(report),
        reply_markup=back_menu(),
        edit_message_id=status.message_id,
    )


register_media_hint(router, ExpressAnalysis.waiting_own, ExpressAnalysis.waiting_rival)
