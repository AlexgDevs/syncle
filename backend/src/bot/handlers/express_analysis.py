from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.bot.delivery import AiogramResultSink
from src.bot.polling import get_job_runner
from src.bot.keyboards.inline import back_menu, express_setup
from src.bot.renderers import render_analysis_report
from src.bot.texts import (
    ANALYSIS_LOADING,
    EXPRESS_OWN_PROMPT,
    EXPRESS_RIVAL_PROMPT,
    INVALID_INPUT,
    MEDIA_HINT,
)
from src.bot.utils import is_valid_card_input
from src.core.results import ResultSink
from src.core.settings import get_settings
from src.modules.analytics import get_analytics_service
from src.modules.analytics.jobs import ANALYSIS_JOB_TYPE

router = Router(name="express_analysis")


class ExpressAnalysis(StatesGroup):
    waiting_own = State()
    waiting_rival = State()


async def _edit_or_pass(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data == "scene:express")
async def start_analysis(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(ExpressAnalysis.waiting_own)
    await _edit_or_pass(callback.message, EXPRESS_OWN_PROMPT, express_setup())
    await callback.answer()


@router.callback_query(F.data == "scene:express:skip")
async def skip_own(callback: CallbackQuery, state: FSMContext) -> None:
    if (await state.get_state()) != ExpressAnalysis.waiting_own.state:
        await callback.answer()
        return
    await state.update_data(own=None)
    await state.set_state(ExpressAnalysis.waiting_rival)
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await _edit_or_pass(callback.message, EXPRESS_RIVAL_PROMPT, back_menu())
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
    status = await message.answer(ANALYSIS_LOADING)
    if get_settings().JOBS_MODE == "taskiq":
        await get_job_runner().submit(
            ANALYSIS_JOB_TYPE,
            {
                "own": own,
                "rival": value,
                "chat_id": message.chat.id,
                "status_message_id": status.message_id,
            },
        )
        await state.clear()
        return
    report = await get_analytics_service().compare_cards(own, value)
    await state.clear()
    if message.bot is None:
        raise RuntimeError("telegram bot instance is not available")
    sink: ResultSink = AiogramResultSink(message.bot)
    await sink.deliver(
        message.chat.id,
        render_analysis_report(report),
        reply_markup=back_menu(),
        edit_message_id=status.message_id,
    )


@router.message(ExpressAnalysis.waiting_own)
async def handle_own_media(message: Message) -> None:
    await message.answer(MEDIA_HINT)


@router.message(ExpressAnalysis.waiting_rival)
async def handle_rival_media(message: Message) -> None:
    await message.answer(MEDIA_HINT)
