"""Deep niche scan scene (issue #44): marketplace, query, own card, job."""

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
from src.bot.keyboards.inline import back_menu, deep_scan_mp, deep_scan_own_setup
from src.bot.niche_delivery import deliver_niche_report
from src.bot.texts import (
    DEEP_INVALID_QUERY,
    DEEP_LOADING,
    DEEP_MP_PROMPT,
    DEEP_OWN_PROMPT,
    DEEP_QUERY_PROMPT,
    INVALID_INPUT,
)
from src.bot.utils import is_valid_card_input, safe_edit
from src.modules.analytics import get_analytics_service
from src.modules.analytics.enums import MARKETPLACES
from src.modules.analytics.jobs import NICHE_SCAN_JOB_TYPE

router = Router(name="deep_scan")

_MIN_QUERY_LEN = 2
_MP_CALLBACK_PREFIX = "scene:deep_scan:mp:"


class DeepScan(StatesGroup):
    waiting_mp = State()
    waiting_query = State()
    waiting_own = State()


@router.callback_query(F.data == "scene:deep_scan")
async def start_deep_scan(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(DeepScan.waiting_mp)
    await safe_edit(callback.message, DEEP_MP_PROMPT, deep_scan_mp())
    await callback.answer()


@router.callback_query(F.data.startswith(_MP_CALLBACK_PREFIX))
async def pick_marketplace(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, DeepScan.waiting_mp, callback):
        return
    marketplace = (callback.data or "").removeprefix(_MP_CALLBACK_PREFIX)
    if marketplace not in MARKETPLACES or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.update_data(marketplace=marketplace)
    await state.set_state(DeepScan.waiting_query)
    await safe_edit(callback.message, DEEP_QUERY_PROMPT, back_menu())
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


@router.callback_query(F.data == "scene:deep_scan:skip")
async def skip_own(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, DeepScan.waiting_own, callback):
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


async def _launch(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    marketplace = data.get("marketplace")
    query = data.get("query")
    if marketplace not in MARKETPLACES or not isinstance(query, str):
        await state.clear()
        await message.answer(DEEP_INVALID_QUERY)
        return
    own = data.get("own")
    own_source = own if isinstance(own, str) else None
    status = await message.answer(DEEP_LOADING)
    if await launch_job_or_inline(
        state,
        NICHE_SCAN_JOB_TYPE,
        {
            "marketplace": marketplace,
            "query": query,
            "own": own_source,
            "chat_id": message.chat.id,
            "status_message_id": status.message_id,
        },
    ):
        return
    report = await get_analytics_service().scan_niche(
        str(marketplace),
        query,
        own_source=own_source,
    )
    await state.clear()
    await deliver_niche_report(
        result_sink(message),
        message.chat.id,
        report,
        status_message_id=status.message_id,
        reply_markup=back_menu(),
    )


register_media_hint(router, DeepScan.waiting_query, DeepScan.waiting_own)
