"""Review audit scene (issues #31, #32): sources, tone, selection, analysis.

The own/rival source accepts a marketplace link/article (reviews are
fetched interactively so the user can pick them) or free text. Tone is
chosen before review selection; the actual LLM analysis runs as the
``reviews_analysis`` job (taskiq) or inline.
"""

import logging
from typing import Any, Literal

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.errors import describe_error
from src.bot.handlers.common import (
    launch_job_or_inline,
    register_media_hint,
    require_state,
    result_sink,
)
from src.bot.keyboards.inline import (
    back_menu,
    reviews_result_keyboard,
    reviews_rival_setup,
    reviews_selection,
    reviews_tone,
)
from src.bot.renderers import render_reviews_report
from src.bot.texts import (
    PROGRESS_STEPS,
    REVIEWS_BUTTONS_HINT,
    REVIEWS_EMPTY_SELECTION,
    REVIEWS_FETCHING,
    REVIEWS_INPUT_HINT,
    REVIEWS_LOADING,
    REVIEWS_NO_REVIEWS,
    REVIEWS_NO_SOURCES,
    REVIEWS_OWN_PROMPT,
    REVIEWS_RIVAL_PROMPT,
    REVIEWS_SELECTION_PROMPT,
    REVIEWS_TEXT_SHORT,
    REVIEWS_TONE_PROMPT,
)
from src.bot.utils import is_valid_card_input, safe_edit
from src.core.errors import SyncleError
from src.modules.analytics.schemas import Review
from src.modules.reviews import (
    ReviewAnalysisRequest,
    ReviewSource,
    Tone,
    fetch_reviews,
    get_reviews_service,
)
from src.modules.reviews.jobs import REVIEWS_JOB_TYPE

logger = logging.getLogger(__name__)
router = Router(name="reviews")

_TONE_PREFIX = "scene:reviews:tone:"
_TOGGLE_PREFIX = "scene:reviews:toggle:"
_PAGE_PREFIX = "scene:reviews:page:"
_MIN_TEXT_LEN = 10
_TONE_VALUES = {tone.value for tone in Tone}
Roles = tuple[Literal["own", "rival"], ...]
_ROLES: Roles = ("own", "rival")


class ReviewsScene(StatesGroup):
    waiting_own = State()
    waiting_rival = State()
    waiting_tone = State()
    waiting_selection = State()


@router.callback_query(F.data == "scene:reviews")
async def start_reviews(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(ReviewsScene.waiting_own)
    await safe_edit(callback.message, REVIEWS_OWN_PROMPT, back_menu())
    await callback.answer()


@router.message(ReviewsScene.waiting_own, F.text)
async def handle_own(message: Message, state: FSMContext) -> None:
    await _handle_source(message, state, "own", message.text or "")


@router.message(ReviewsScene.waiting_rival, F.text)
async def handle_rival(message: Message, state: FSMContext) -> None:
    await _handle_source(message, state, "rival", message.text or "")


async def _handle_source(
    message: Message, state: FSMContext, role: str, raw: str
) -> None:
    value = raw.strip()
    if is_valid_card_input(value):
        await _fetch_source(message, state, role, value)
        return
    if len(value) < _MIN_TEXT_LEN:
        await message.answer(REVIEWS_TEXT_SHORT)
        return
    updates: dict[str, Any] = {
        f"{role}_description": value,
        f"{role}_reviews": [],
    }
    await state.update_data(**updates)
    await _after_source(message, state, role, edit=False)


async def _fetch_source(
    message: Message, state: FSMContext, role: str, source: str
) -> None:
    """Fetch marketplace reviews; failures edit the status message in place."""
    status = await message.answer(REVIEWS_FETCHING)
    try:
        reviews = await fetch_reviews(source)
    except SyncleError as exc:
        await safe_edit(status, describe_error(exc))
        return
    if not reviews:
        await safe_edit(status, REVIEWS_NO_REVIEWS)
        return
    updates: dict[str, Any] = {
        f"{role}_source": source,
        f"{role}_description": None,
        f"{role}_reviews": [review.model_dump(mode="json") for review in reviews],
    }
    await state.update_data(**updates)
    await _after_source(status, state, role, edit=True)


async def _after_source(
    target: Message, state: FSMContext, role: str, *, edit: bool
) -> None:
    """Advance to the next step; fetch flows edit the status message in place."""
    if role == "own":
        next_state = ReviewsScene.waiting_rival
        prompt = REVIEWS_RIVAL_PROMPT
        markup = reviews_rival_setup()
    else:
        next_state = ReviewsScene.waiting_tone
        prompt = REVIEWS_TONE_PROMPT
        markup = reviews_tone()
    await state.set_state(next_state)
    if edit:
        await safe_edit(target, prompt, markup)
    else:
        await target.answer(prompt, reply_markup=markup)


@router.callback_query(F.data == "scene:reviews:skip")
async def skip_rival(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, ReviewsScene.waiting_rival, callback):
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(ReviewsScene.waiting_tone)
    await safe_edit(callback.message, REVIEWS_TONE_PROMPT, reviews_tone())
    await callback.answer()


@router.callback_query(F.data.startswith(_TONE_PREFIX))
async def pick_tone(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, ReviewsScene.waiting_tone, callback):
        return
    tone = (callback.data or "").removeprefix(_TONE_PREFIX)
    if tone not in _TONE_VALUES or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.update_data(tone=tone, selected=[], page=0)
    entries = _entries(await state.get_data())
    if entries:
        selected = {key for key, _ in entries}
        await state.update_data(selected=sorted(selected))
        await state.set_state(ReviewsScene.waiting_selection)
        await safe_edit(
            callback.message,
            REVIEWS_SELECTION_PROMPT.format(count=len(entries)),
            reviews_selection(entries, selected, page=0),
        )
        await callback.answer()
        return
    await callback.answer()
    await _launch(callback.message, state)


@router.callback_query(F.data.startswith(_PAGE_PREFIX))
async def select_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, ReviewsScene.waiting_selection, callback):
        return
    raw_page = (callback.data or "").removeprefix(_PAGE_PREFIX)
    if not isinstance(callback.message, Message) or not raw_page.isdigit():
        await callback.answer()
        return
    page = int(raw_page)
    data = await state.get_data()
    await state.update_data(page=page)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=reviews_selection(
                _entries(data), set(_selected(data)), page=page
            )
        )
    except TelegramBadRequest:
        logger.debug("page markup unchanged")
    await callback.answer()


@router.callback_query(F.data == "scene:reviews:noop")
async def page_counter(callback: CallbackQuery) -> None:
    """Inert page counter button: just ack the tap."""
    await callback.answer()


@router.callback_query(F.data.startswith(_TOGGLE_PREFIX))
async def toggle_review(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, ReviewsScene.waiting_selection, callback):
        return
    key = (callback.data or "").removeprefix(_TOGGLE_PREFIX)
    data = await state.get_data()
    selected = _selected(data)
    if key in selected:
        selected.remove(key)
    else:
        selected.append(key)
    await state.update_data(selected=selected)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(
                reply_markup=reviews_selection(
                    _entries(data), set(selected), page=_page(data)
                )
            )
        except TelegramBadRequest:
            logger.debug("selection markup unchanged")
    await callback.answer()


@router.callback_query(F.data == "scene:reviews:analyze")
async def analyze_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, ReviewsScene.waiting_selection, callback):
        return
    if not _selected(await state.get_data()):
        await callback.answer(REVIEWS_EMPTY_SELECTION, show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    # Ack before the LLM flow: callbacks expire while we wait.
    await callback.answer()
    await _launch(callback.message, state)


def _selected(data: dict[str, object]) -> list[str]:
    raw = data.get("selected")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _page(data: dict[str, object]) -> int:
    raw = data.get("page")
    return raw if isinstance(raw, int) and raw >= 0 else 0


def _entries(data: dict[str, object]) -> list[tuple[str, Review]]:
    """Role-prefixed keys ``o:<id>`` / ``r:<id>`` keep selection ids unique."""
    entries: list[tuple[str, Review]] = []
    for role in _ROLES:
        raw = data.get(f"{role}_reviews")
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                review = Review.model_validate(item)
                entries.append((f"{role[0]}:{review.review_id}", review))
    return entries


async def _launch(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    tone_raw = data.get("tone")
    if not isinstance(tone_raw, str) or tone_raw not in _TONE_VALUES:
        await state.set_state(ReviewsScene.waiting_tone)
        await message.answer(REVIEWS_TONE_PROMPT, reply_markup=reviews_tone())
        return
    selected = set(_selected(data))
    sources = _build_sources(data, selected)
    if not sources:
        await state.clear()
        await message.answer(REVIEWS_NO_SOURCES)
        return
    request = ReviewAnalysisRequest(tone=Tone(tone_raw), sources=sources)
    status = await message.answer(REVIEWS_LOADING)
    if await launch_job_or_inline(
        state,
        REVIEWS_JOB_TYPE,
        {
            **request.model_dump(mode="json"),
            "chat_id": message.chat.id,
            "status_message_id": status.message_id,
        },
    ):
        return
    sink = result_sink(message)

    async def on_progress(step: str) -> None:
        await sink.deliver(
            message.chat.id,
            PROGRESS_STEPS.get(step, REVIEWS_LOADING),
            edit_message_id=status.message_id,
        )

    report = await get_reviews_service().analyze(request, on_progress=on_progress)
    await state.clear()
    await sink.deliver(
        message.chat.id,
        render_reviews_report(report),
        reply_markup=reviews_result_keyboard(report),
        edit_message_id=status.message_id,
    )


def _build_sources(data: dict[str, object], selected: set[str]) -> list[ReviewSource]:
    """Own and rival sources; reviews are filtered by the selection (#32)."""
    sources: list[ReviewSource] = []
    for role in _ROLES:
        description = data.get(f"{role}_description")
        desc = (
            description
            if isinstance(description, str) and description.strip()
            else None
        )
        reviews = _role_reviews(data, role, selected)
        if desc or reviews:
            sources.append(ReviewSource(role=role, description=desc, reviews=reviews))
    return sources


def _role_reviews(
    data: dict[str, object], role: Literal["own", "rival"], selected: set[str]
) -> list[Review]:
    raw = data.get(f"{role}_reviews")
    if not isinstance(raw, list):
        return []
    reviews = [Review.model_validate(item) for item in raw if isinstance(item, dict)]
    if selected:
        return [r for r in reviews if f"{role[0]}:{r.review_id}" in selected]
    return reviews


register_media_hint(
    router,
    ReviewsScene.waiting_own,
    ReviewsScene.waiting_rival,
    hint=REVIEWS_INPUT_HINT,
)

register_media_hint(
    router,
    ReviewsScene.waiting_tone,
    ReviewsScene.waiting_selection,
    hint=REVIEWS_BUTTONS_HINT,
)
