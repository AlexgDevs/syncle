"""Infographics scene (issue #62, M7-v5): style -> brief -> photos -> job.

The entry point is a button on the SEO result keyboard; the report
itself is recovered from the Redis stash (both delivery paths clear FSM
state before the button can be pressed). After the style pick the
customer must describe the poster (what to show, exact wording — M7-v5)
and may send product photos: exactly ``PHOTO_CAP`` photos or none at
all (the skip button falls back to the SEO stash photo). The third
photo launches the render automatically; 0-2 accumulated photos are
used as they are. The brief plus downloaded photos land in their own
stash key; the ``infographics_render`` job payload stays light —
chat_id, variant, status_message_id. Delivery is a photo.
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from src.bot.handlers.common import (
    launch_job_or_inline,
    register_media_hint,
    require_state,
    result_sink,
)
from src.bot.keyboards.inline import (
    back_menu,
    infographic_photo_setup,
    infographic_variants,
)
from src.bot.photos import PHOTO_CAP, append_photo_id, clean_file_ids, download_photos
from src.bot.renderers import render_infographic_caption
from src.bot.texts import (
    INFO_BRIEF_PROMPT,
    INFO_BRIEF_REQUIRED,
    INFO_FAILED,
    INFO_HINT,
    INFO_LOADING,
    INFO_NEED_SEO,
    INFO_PHOTO_DONE,
    INFO_PHOTO_HINT,
    INFO_PHOTO_PROMPT,
    INFO_PHOTO_RECEIVED,
    INFO_PROMPT,
    INFO_STASH_EXPIRED,
    PROGRESS_STEPS,
)
from src.bot.utils import safe_edit
from src.core.errors import SyncleError
from src.core.stash import load_stashed_entry, load_stashed_seo, stash_brief
from src.modules.content import SeoText
from src.modules.infographics import (
    InfographicRequest,
    StyleVariant,
    get_infographics_service,
)
from src.modules.infographics.jobs import INFOGRAPHICS_JOB_TYPE

logger = logging.getLogger(__name__)

router = Router(name="infographics")

VARIANT_PREFIX = "scene:infographics:variant:"

SKIP_PHOTO = "scene:infographics:skip_photo"

FILENAME = "infographic.png"

_MIN_BRIEF_LEN = 5


class InfographicsScene(StatesGroup):
    waiting_variant = State()
    waiting_brief = State()
    waiting_photo = State()


@router.callback_query(F.data == "scene:infographics")
async def start_infographics(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    message = callback.message
    seo = await load_stashed_seo(message.chat.id)
    if seo is None:
        await callback.answer(INFO_NEED_SEO, show_alert=True)
        return
    await state.clear()
    await state.set_state(InfographicsScene.waiting_variant)
    # a fresh picker message: the SEO report stays intact for copying
    await message.answer(INFO_PROMPT, reply_markup=infographic_variants())
    await callback.answer()


@router.callback_query(F.data.startswith(VARIANT_PREFIX))
async def pick_variant(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, InfographicsScene.waiting_variant, callback):
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    message = callback.message
    raw = (callback.data or "").removeprefix(VARIANT_PREFIX)
    try:
        variant = StyleVariant(raw)
    except ValueError:
        await callback.answer()
        return
    if await load_stashed_entry(message.chat.id) is None:
        # the picker is already open — the stash died mid-scene (#62)
        await callback.answer(INFO_STASH_EXPIRED, show_alert=True)
        return
    # the customer's brief is required (M7-v5): ask before rendering
    await state.update_data(variant=variant.value)
    await state.set_state(InfographicsScene.waiting_brief)
    await safe_edit(message, INFO_BRIEF_PROMPT, back_menu())
    await callback.answer()


@router.message(InfographicsScene.waiting_brief, F.text)
async def handle_brief(message: Message, state: FSMContext) -> None:
    brief = (message.text or "").strip()
    if len(brief) < _MIN_BRIEF_LEN:
        await message.answer(INFO_BRIEF_REQUIRED)
        return
    await state.update_data(brief=brief)
    await state.set_state(InfographicsScene.waiting_photo)
    data = await state.get_data()
    if len(clean_file_ids(data.get("photos"))) >= PHOTO_CAP:
        # the full set arrived before the text — render right away
        await _launch(message, state)
        return
    await message.answer(INFO_PHOTO_PROMPT, reply_markup=infographic_photo_setup())


async def _accumulate_photo(message: Message, state: FSMContext) -> list[str] | None:
    """Keep the photo file_id in FSM; confirm each photo (album = once).

    Returns the updated list, or None when nothing was stored (no photo
    or the cap already reached).
    """
    photo_sizes = message.photo
    if not photo_sizes:
        return None
    data = await state.get_data()
    photos = append_photo_id(
        clean_file_ids(data.get("photos")), photo_sizes[-1].file_id
    )
    if photos is None:
        return None
    group = message.media_group_id
    await state.update_data(photos=photos, media_group=group)
    if group is None or group != data.get("media_group"):
        if len(photos) >= PHOTO_CAP:
            await message.answer(
                INFO_PHOTO_DONE.format(index=len(photos), cap=PHOTO_CAP)
            )
        else:
            await message.answer(
                INFO_PHOTO_RECEIVED.format(
                    index=len(photos), cap=PHOTO_CAP, left=PHOTO_CAP - len(photos)
                )
            )
    return photos


@router.message(InfographicsScene.waiting_brief, F.photo)
async def handle_brief_photo(message: Message, state: FSMContext) -> None:
    # photos may arrive before the text — keep them for the launch
    await _accumulate_photo(message, state)


@router.message(InfographicsScene.waiting_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    photos = await _accumulate_photo(message, state)
    if photos is not None and len(photos) >= PHOTO_CAP:
        # the third photo completes the set — no extra button press
        await _launch(message, state)


@router.callback_query(F.data == SKIP_PHOTO)
async def skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, InfographicsScene.waiting_photo, callback):
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    # Ack before the slow download/LLM flow: callbacks expire while we wait.
    await callback.answer()
    await _launch(callback.message, state)


async def _launch(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    brief = data.get("brief")
    variant = data.get("variant")
    if (
        not isinstance(brief, str)
        or len(brief.strip()) < _MIN_BRIEF_LEN
        or not isinstance(variant, str)
    ):
        await state.clear()
        await message.answer(INFO_BRIEF_REQUIRED)
        return
    file_ids = clean_file_ids(data.get("photos"))[:PHOTO_CAP]

    status = await message.answer(INFO_LOADING)

    # one download pass: image input and the brief stash (M7-v5)
    downloaded: list[bytes] = []
    if file_ids and message.bot is not None:
        try:
            downloaded = await download_photos(message.bot, file_ids)
        except TelegramAPIError:
            logger.warning("photo download failed", exc_info=True)

    # the job (taskiq path) reads the brief by chat_id; payload stays light
    await stash_brief(message.chat.id, brief.strip(), downloaded)

    if await launch_job_or_inline(
        state,
        INFOGRAPHICS_JOB_TYPE,
        {
            "chat_id": message.chat.id,
            "variant": variant,
            "status_message_id": status.message_id,
        },
    ):
        return

    entry = await load_stashed_entry(message.chat.id)
    if entry is None:
        await state.clear()
        await safe_edit(message, INFO_STASH_EXPIRED)
        return
    sink = result_sink(message)

    async def on_progress(step: str) -> None:
        await sink.deliver(
            message.chat.id,
            PROGRESS_STEPS.get(step, INFO_LOADING),
            edit_message_id=status.message_id,
        )

    request = InfographicRequest(
        seo=SeoText.model_validate(entry.seo), variant=StyleVariant(variant)
    )
    try:
        artwork = await get_infographics_service().render(
            request,
            photos=downloaded or entry.photos or None,
            brief=brief.strip(),
            on_progress=on_progress,
        )
    except SyncleError as exc:
        # the status message carries the error; the dispatcher would duplicate it
        logger.warning("infographic render failed: %s", exc)
        await safe_edit(message, INFO_FAILED)
        return
    await state.clear()
    await sink.deliver_photo(
        message.chat.id,
        render_infographic_caption(StyleVariant(variant)),
        artwork,
        filename=FILENAME,
        reply_markup=infographic_variants(),
        edit_message_id=status.message_id,
    )


register_media_hint(router, InfographicsScene.waiting_variant, hint=INFO_HINT)
register_media_hint(router, InfographicsScene.waiting_brief, hint=INFO_BRIEF_REQUIRED)
register_media_hint(router, InfographicsScene.waiting_photo, hint=INFO_PHOTO_HINT)
