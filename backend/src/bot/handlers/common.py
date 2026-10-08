"""Shared helpers for scene handlers (FSM guards, job launch, delivery)."""

from typing import Any

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from src.bot.delivery import AiogramResultSink
from src.bot.polling import get_job_runner
from src.bot.texts import MEDIA_HINT
from src.core.results import ResultSink
from src.core.settings import get_settings


async def require_state(
    state: FSMContext, expected: State, callback: CallbackQuery
) -> bool:
    """True when the FSM is in ``expected``; otherwise ack the callback and stop."""
    if (await state.get_state()) != expected.state:
        await callback.answer()
        return False
    return True


def register_media_hint(router: Router, *states: State, hint: str = MEDIA_HINT) -> None:
    """Reply ``hint`` to non-text messages in the given states.

    Register after the state's text handlers so they win the match.
    """

    @router.message(StateFilter(*states))
    async def _media_hint(message: Message) -> None:
        await message.answer(hint)


async def launch_job_or_inline(
    state: FSMContext, job_type: str, payload: dict[str, Any]
) -> bool:
    """Submit a job in taskiq mode (FSM cleared, caller stops) or run inline.

    Returns True when the job was handed to taskiq.
    """
    if get_settings().JOBS_MODE != "taskiq":
        return False
    await get_job_runner().submit(job_type, payload)
    await state.clear()
    return True


def result_sink(message: Message) -> ResultSink:
    """Aiogram ResultSink bound to the message's bot instance."""
    if message.bot is None:
        raise RuntimeError("telegram bot instance is not available")
    return AiogramResultSink(message.bot)
