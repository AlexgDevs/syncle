"""Finance scenes (M5, #48/#52): quick unit calc and settlement report.

Scene A (#48) is a four-step inline FSM that runs the deterministic
calculator locally. Scene B (#52) downloads the uploaded report, keeps
it in the Redis stash and submits ``finance_report`` with an inline
fallback — same pattern as the legal audit.
"""

import io
import logging
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.errors import describe_error
from src.bot.finance_delivery import deliver_report_analysis
from src.bot.handlers.common import (
    launch_job_or_inline,
    register_media_hint,
    require_state,
    result_sink,
)
from src.bot.keyboards.inline import back_menu, finance_calc_result
from src.bot.renderers import render_unit_calc_report
from src.bot.texts import (
    FIN_CALC_START,
    FIN_COST_PROMPT,
    FIN_EXPENSES_PROMPT,
    FIN_INVALID_NON_NEGATIVE,
    FIN_INVALID_POSITIVE,
    FIN_INVALID_QUANTITY,
    FIN_NUMBER_HINT,
    FIN_QUANTITY_PROMPT,
    FIN_REPORT_DOWNLOAD_FAILED,
    FIN_REPORT_EMPTY,
    FIN_REPORT_LOADING,
    FIN_REPORT_PROMPT,
    FIN_REPORT_TOO_BIG,
    FIN_REPORT_UNSUPPORTED,
    PROGRESS_STEPS,
)
from src.bot.utils import safe_edit
from src.core.errors import SyncleError
from src.core.settings import get_settings
from src.core.stash import stash_report
from src.modules.finance import UnitInputs, get_finance_service
from src.modules.finance.calculator import money
from src.modules.finance.jobs import FINANCE_JOB_TYPE
from src.modules.finance.report import SUPPORTED_SUFFIXES, parse_money
from src.modules.finance.schemas import FinanceReportPayload

logger = logging.getLogger(__name__)
router = Router(name="finance")

FIN_REPORT_HINT = "Отправьте файлом: XLSX, CSV или PDF."

# what-if scenarios (#47): price delta, quantity delta, RU label
_WIF_DELTAS: dict[str, tuple[Decimal, Decimal, str]] = {
    "price_up": (Decimal("10"), Decimal("0"), "цена +10%"),
    "price_down": (Decimal("-10"), Decimal("0"), "цена −10%"),
    "qty_up": (Decimal("0"), Decimal("10"), "объём +10%"),
    "qty_down": (Decimal("0"), Decimal("-10"), "объём −10%"),
}


class FinanceCalcScene(StatesGroup):
    waiting_price = State()
    waiting_cost = State()
    waiting_expenses = State()
    waiting_quantity = State()
    result = State()


class FinanceReportScene(StatesGroup):
    waiting_document = State()


# --- scene A: quick unit calc (#48) ---


@router.callback_query(F.data == "scene:finance:calc")
async def start_calc(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(FinanceCalcScene.waiting_price)
    await safe_edit(callback.message, FIN_CALC_START, back_menu())
    await callback.answer()


@router.message(FinanceCalcScene.waiting_price, F.text)
async def handle_price(message: Message, state: FSMContext) -> None:
    value = parse_money((message.text or "").strip())
    if value is None or value <= 0:
        await message.answer(FIN_INVALID_POSITIVE)
        return
    await state.update_data(price=str(value))
    await state.set_state(FinanceCalcScene.waiting_cost)
    await message.answer(FIN_COST_PROMPT, reply_markup=back_menu())


@router.message(FinanceCalcScene.waiting_cost, F.text)
async def handle_cost(message: Message, state: FSMContext) -> None:
    value = parse_money((message.text or "").strip())
    if value is None or value < 0:
        await message.answer(FIN_INVALID_NON_NEGATIVE)
        return
    await state.update_data(unit_cost=str(value))
    await state.set_state(FinanceCalcScene.waiting_expenses)
    await message.answer(FIN_EXPENSES_PROMPT, reply_markup=back_menu())


@router.message(FinanceCalcScene.waiting_expenses, F.text)
async def handle_expenses(message: Message, state: FSMContext) -> None:
    value = parse_money((message.text or "").strip())
    if value is None or value < 0:
        await message.answer(FIN_INVALID_NON_NEGATIVE)
        return
    await state.update_data(unit_expenses=str(value))
    await state.set_state(FinanceCalcScene.waiting_quantity)
    await message.answer(FIN_QUANTITY_PROMPT, reply_markup=back_menu())


@router.message(FinanceCalcScene.waiting_quantity, F.text)
async def handle_quantity(message: Message, state: FSMContext) -> None:
    value = parse_money((message.text or "").strip())
    if value is None or value <= 0 or value != value.to_integral_value():
        await message.answer(FIN_INVALID_QUANTITY)
        return
    data = await state.get_data()
    inputs = UnitInputs(
        price=Decimal(str(data.get("price", "0"))),
        unit_cost=Decimal(str(data.get("unit_cost", "0"))),
        unit_expenses=Decimal(str(data.get("unit_expenses", "0"))),
        quantity=value,
    )
    report = get_finance_service().calc(inputs)
    await state.update_data(inputs=inputs.model_dump(mode="json"))
    await state.set_state(FinanceCalcScene.result)
    await message.answer(
        render_unit_calc_report(inputs, report),
        reply_markup=finance_calc_result(inputs, report),
    )


@router.callback_query(F.data.startswith("scene:finance:calc:"))
async def handle_what_if(callback: CallbackQuery, state: FSMContext) -> None:
    key = (callback.data or "").removeprefix("scene:finance:calc:")
    scenario = _WIF_DELTAS.get(key)
    if scenario is None:
        await callback.answer()
        return
    if not await require_state(state, FinanceCalcScene.result, callback):
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    data = await state.get_data()
    raw = data.get("inputs")
    if not isinstance(raw, dict):
        await callback.answer()
        return
    inputs = UnitInputs.model_validate(raw)
    price_delta, quantity_delta, label = scenario
    # display inputs mirror what_if()'s quantized scenario (copy button)
    scenario_inputs = inputs.model_copy(
        update={
            "price": money(
                inputs.price * (Decimal("1") + price_delta / Decimal("100"))
            ),
            "quantity": money(
                inputs.quantity * (Decimal("1") + quantity_delta / Decimal("100"))
            ),
        }
    )
    report = get_finance_service().what_if(
        inputs,
        price_delta_pct=price_delta,
        quantity_delta_pct=quantity_delta,
    )
    await safe_edit(
        callback.message,
        render_unit_calc_report(scenario_inputs, report, scenario=label),
        finance_calc_result(scenario_inputs, report),
    )
    await callback.answer()


register_media_hint(
    router,
    FinanceCalcScene.waiting_price,
    FinanceCalcScene.waiting_cost,
    FinanceCalcScene.waiting_expenses,
    FinanceCalcScene.waiting_quantity,
    hint=FIN_NUMBER_HINT,
)


# --- scene B: settlement report analysis (#52) ---


@router.callback_query(F.data == "scene:finance:report")
async def start_report(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(FinanceReportScene.waiting_document)
    await safe_edit(callback.message, FIN_REPORT_PROMPT, back_menu())
    await callback.answer()


def _report_filename(message: Message) -> str:
    if message.document is None or not message.document.file_name:
        return ""
    return message.document.file_name


def _report_supported(filename: str) -> bool:
    lowered = filename.lower()
    return any(lowered.endswith(suffix) for suffix in SUPPORTED_SUFFIXES)


def _too_big(size: int | None) -> bool:
    cap = get_settings().FINANCE_REPORT_MAX_BYTES
    return size is not None and size > cap


@router.message(FinanceReportScene.waiting_document, F.document)
async def handle_report_document(message: Message, state: FSMContext) -> None:
    filename = _report_filename(message)
    if not filename or not _report_supported(filename):
        await message.answer(
            FIN_REPORT_UNSUPPORTED.format(filename=filename or "без имени")
        )
        return
    if message.document is None or message.bot is None:
        await message.answer(FIN_REPORT_DOWNLOAD_FAILED.format(filename=filename))
        return
    if _too_big(message.document.file_size):
        cap_mb = get_settings().FINANCE_REPORT_MAX_BYTES // (1024 * 1024)
        await message.answer(FIN_REPORT_TOO_BIG.format(mb=cap_mb))
        return
    try:
        file = await message.bot.get_file(message.document.file_id)
        buffer = io.BytesIO()
        await message.bot.download(file, destination=buffer)
        downloaded = buffer.getvalue()
    except Exception:  # noqa: BLE001
        logger.warning("finance report download failed", exc_info=True)
        await message.answer(FIN_REPORT_DOWNLOAD_FAILED.format(filename=filename))
        return
    if not downloaded:
        await message.answer(FIN_REPORT_DOWNLOAD_FAILED.format(filename=filename))
        return
    cap = get_settings().FINANCE_REPORT_MAX_BYTES
    if len(downloaded) > cap:
        await message.answer(FIN_REPORT_TOO_BIG.format(mb=cap // (1024 * 1024)))
        return
    status = await message.answer(FIN_REPORT_LOADING)
    await stash_report(message.chat.id, filename, downloaded)
    payload = FinanceReportPayload(
        chat_id=message.chat.id,
        status_message_id=status.message_id,
        filename=filename,
    )
    if await launch_job_or_inline(
        state, FINANCE_JOB_TYPE, payload.model_dump(mode="json")
    ):
        return
    sink = result_sink(message)

    async def on_progress(step: str) -> None:
        await sink.deliver(
            message.chat.id,
            PROGRESS_STEPS.get(step, FIN_REPORT_LOADING),
            edit_message_id=status.message_id,
        )

    try:
        analysis = await get_finance_service().analyze(
            downloaded, filename=filename, on_progress=on_progress
        )
    except SyncleError as exc:
        await safe_edit(status, describe_error(exc))
        return
    except Exception:  # noqa: BLE001
        logger.exception("inline finance report analysis failed")
        await safe_edit(status, FIN_REPORT_EMPTY)
        return
    await state.clear()
    await deliver_report_analysis(
        sink,
        message.chat.id,
        analysis,
        status_message_id=status.message_id,
        reply_markup=back_menu(),
    )


register_media_hint(router, FinanceReportScene.waiting_document, hint=FIN_REPORT_HINT)
