"""Deep niche scan scene (issue #44): marketplace, query, own card, job."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from src.bot.delivery import AiogramResultSink
from src.bot.keyboards.inline import back_menu, deep_scan_mp, deep_scan_own_setup
from src.bot.niche_delivery import deliver_niche_report
from src.bot.polling import get_job_runner
from src.bot.texts import (
    DEEP_INVALID_QUERY,
    DEEP_LOADING,
    DEEP_MP_PROMPT,
    DEEP_OWN_PROMPT,
    DEEP_QUERY_PROMPT,
    INVALID_INPUT,
    MEDIA_HINT,
)
from src.bot.utils import is_valid_card_input
from src.core.results import ResultSink
from src.core.settings import get_settings
from src.modules.analytics import get_analytics_service
from src.modules.analytics.jobs import NICHE_SCAN_JOB_TYPE

router = Router(name="deep_scan")

_MIN_QUERY_LEN = 2
_MARKETPLACES = ("wb", "ozon")


class DeepScan(StatesGroup):
    waiting_mp = State()
    waiting_query = State()
    waiting_own = State()


async def _edit_or_pass(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


@router.callback_query(F.data == "scene:deep_scan")
async def start_deep_scan(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(DeepScan.waiting_mp)
    await _edit_or_pass(callback.message, DEEP_MP_PROMPT, deep_scan_mp())
    await callback.answer()


@router.callback_query(F.data.startswith("scene:deep:mp:"))
async def pick_marketplace(callback: CallbackQuery, state: FSMContext) -> None:
    if (await state.get_state()) != DeepScan.waiting_mp.state:
        await callback.answer()
        return
    marketplace = (callback.data or "").removeprefix("scene:deep:mp:")
    if marketplace not in _MARKETPLACES or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.update_data(marketplace=marketplace)
    await state.set_state(DeepScan.waiting_query)
    await _edit_or_pass(callback.message, DEEP_QUERY_PROMPT, back_menu())
    await callback.answer()


@router.message(DeepScan.waiting_query, F.text)
async def handle_query(message: Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if len(query) < _MIN_QUERY_LEN:
        await message.answer(DEEP_INVALID_QUERY)
        return
    await state.update_data(query=query)
    await state.set_state(DeepScan.waiting_own)
    await message.answer(DEEP_OWN_PROMPT, reply_markup=deep_scan_own_setup())


@router.callback_query(F.data == "scene:deep:skip")
async def skip_own(callback: CallbackQuery, state: FSMContext) -> None:
    if (await state.get_state()) != DeepScan.waiting_own.state:
        await callback.answer()
        return
    await state.update_data(own=None)
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await _launch(callback.message, state)
    await callback.answer()


@router.message(DeepScan.waiting_own, F.text)
async def handle_own(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not is_valid_card_input(value):
        await message.answer(INVALID_INPUT)
        return
    await state.update_data(own=value)
    await _launch(message, state)


@router.message(DeepScan.waiting_query)
async def handle_query_media(message: Message) -> None:
    await message.answer(MEDIA_HINT)


@router.message(DeepScan.waiting_own)
async def handle_own_media(message: Message) -> None:
    await message.answer(MEDIA_HINT)


async def _launch(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    marketplace = data.get("marketplace")
    query = data.get("query")
    if marketplace not in _MARKETPLACES or not isinstance(query, str):
        await state.clear()
        await message.answer(DEEP_INVALID_QUERY)
        return
    own = data.get("own")
    own_source = own if isinstance(own, str) else None
    status = await message.answer(DEEP_LOADING)
    if get_settings().JOBS_MODE == "taskiq":
        await get_job_runner().submit(
            NICHE_SCAN_JOB_TYPE,
            {
                "marketplace": marketplace,
                "query": query,
                "own": own_source,
                "chat_id": message.chat.id,
                "status_message_id": status.message_id,
            },
        )
        await state.clear()
        return
    report = await get_analytics_service().scan_niche(
        marketplace,
        query,
        own_source=own_source,
    )
    await state.clear()
    if message.bot is None:
        raise RuntimeError("telegram bot instance is not available")
    sink: ResultSink = AiogramResultSink(message.bot)
    await deliver_niche_report(
        sink,
        message.chat.id,
        report,
        status_message_id=status.message_id,
        reply_markup=back_menu(),
    )
