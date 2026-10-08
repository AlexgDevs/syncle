"""SEO text scene (issue #26): marketplace, input+photos, advantages, job.

Photo messages are optional (issue #27): up to three file_ids are kept
in FSM state, downloaded once right before the vision call, and merged
into the request as attributes. Vision failures degrade to text-only
with a RU hint instead of aborting generation.
"""

import io
import logging

from aiogram import Bot, F, Router
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
    seo_keywords_setup,
    seo_mp,
    seo_result_keyboard,
)
from src.bot.renderers import render_seo_report
from src.bot.texts import (
    PROGRESS_STEPS,
    SEO_INPUT_HINT,
    SEO_INPUT_PROMPT,
    SEO_KEYWORDS_PROMPT,
    SEO_LOADING,
    SEO_MP_PROMPT,
    SEO_NO_VISION,
    SEO_PHOTO_LIMIT,
    SEO_PHOTO_RECEIVED,
    SEO_SCANNING,
    SEO_TEXT_REQUIRED,
)
from src.bot.utils import safe_edit
from src.core.llm import LLMError, get_vision_provider
from src.modules.analytics.enums import MARKETPLACES, Marketplace
from src.modules.content import SeoAttributes, SeoRequest, get_seo_service
from src.modules.content.errors import SeoGenerationError
from src.modules.content.jobs import SEO_JOB_TYPE
from src.modules.content.vision import describe_product

logger = logging.getLogger(__name__)
router = Router(name="seo_text")

_MP_CALLBACK_PREFIX = "scene:seo:mp:"
_MAX_PHOTOS = 3
_MAX_ADVANTAGES = 3
_MIN_DESCRIPTION_LEN = 3


class SeoTextScene(StatesGroup):
    waiting_mp = State()
    waiting_input = State()
    waiting_keywords = State()


@router.callback_query(F.data == "scene:seo")
async def start_seo(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(SeoTextScene.waiting_mp)
    await safe_edit(callback.message, SEO_MP_PROMPT, seo_mp())
    await callback.answer()


@router.callback_query(F.data.startswith(_MP_CALLBACK_PREFIX))
async def pick_marketplace(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, SeoTextScene.waiting_mp, callback):
        return
    marketplace = (callback.data or "").removeprefix(_MP_CALLBACK_PREFIX)
    if marketplace not in MARKETPLACES or not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.update_data(marketplace=marketplace)
    await state.set_state(SeoTextScene.waiting_input)
    await safe_edit(callback.message, SEO_INPUT_PROMPT, back_menu())
    await callback.answer()


@router.message(SeoTextScene.waiting_input, F.text)
async def handle_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if len(description) < _MIN_DESCRIPTION_LEN:
        await message.answer(SEO_TEXT_REQUIRED)
        return
    await state.update_data(description=description)
    await state.set_state(SeoTextScene.waiting_keywords)
    await message.answer(SEO_KEYWORDS_PROMPT, reply_markup=seo_keywords_setup())


async def _handle_photo(message: Message, state: FSMContext) -> None:
    """Keep the photo file_id in FSM; confirm the first photo of a group."""
    photo_sizes = message.photo
    if not photo_sizes:
        return
    data = await state.get_data()
    raw_photos = data.get("photos")
    photos = (
        [p for p in raw_photos if isinstance(p, str)]
        if isinstance(raw_photos, list)
        else []
    )
    group = message.media_group_id
    if len(photos) >= _MAX_PHOTOS:
        if group is None or group != data.get("media_group"):
            await message.answer(SEO_PHOTO_LIMIT.format(cap=_MAX_PHOTOS))
        return
    photos.append(photo_sizes[-1].file_id)
    await state.update_data(photos=photos, media_group=group)
    if group is None or group != data.get("media_group"):
        await message.answer(
            SEO_PHOTO_RECEIVED.format(index=len(photos), cap=_MAX_PHOTOS)
        )


@router.message(SeoTextScene.waiting_input, F.photo)
async def handle_input_photo(message: Message, state: FSMContext) -> None:
    await _handle_photo(message, state)


@router.message(SeoTextScene.waiting_keywords, F.photo)
async def handle_keywords_photo(message: Message, state: FSMContext) -> None:
    await _handle_photo(message, state)


@router.message(SeoTextScene.waiting_keywords, F.text)
async def handle_advantages(message: Message, state: FSMContext) -> None:
    await state.update_data(advantages=_split_advantages(message.text or ""))
    await _launch(message, state)


@router.callback_query(F.data == "scene:seo:skip")
async def skip_advantages(callback: CallbackQuery, state: FSMContext) -> None:
    if not await require_state(state, SeoTextScene.waiting_keywords, callback):
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.update_data(advantages=[])
    # Ack before the slow vision/LLM flow: callbacks expire while we wait.
    await callback.answer()
    await _launch(callback.message, state)


def _split_advantages(text: str) -> list[str]:
    parts = [
        part.strip() for part in text.replace(";", ",").replace("\n", ",").split(",")
    ]
    items = [part for part in parts if part]
    return items[:_MAX_ADVANTAGES]


async def _download_photos(bot: Bot, file_ids: list[str]) -> list[bytes]:
    images: list[bytes] = []
    for file_id in file_ids:
        file = await bot.get_file(file_id)
        buffer = io.BytesIO()
        await bot.download(file, destination=buffer)
        images.append(buffer.getvalue())
    return images


async def _describe_photos(
    message: Message, photos: list[str], hint: str
) -> SeoAttributes | None:
    """Vision call, best effort: None on any failure (issue #27)."""
    vision = get_vision_provider()
    if vision is None or message.bot is None:
        return None
    try:
        images = await _download_photos(message.bot, photos)
        return await describe_product(vision, images, hint)
    except (LLMError, SeoGenerationError, TelegramAPIError) as exc:
        logger.warning("vision degraded: %s", type(exc).__name__)
        return None


async def _launch(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    description = data.get("description")
    marketplace = data.get("marketplace")
    if (
        not isinstance(description, str)
        or len(description.strip()) < _MIN_DESCRIPTION_LEN
        or marketplace not in MARKETPLACES
    ):
        await state.clear()
        await message.answer(SEO_TEXT_REQUIRED)
        return
    raw_advantages = data.get("advantages")
    advantages = (
        [a for a in raw_advantages if isinstance(a, str)]
        if isinstance(raw_advantages, list)
        else []
    )
    raw_photos = data.get("photos")
    photos = (
        [p for p in raw_photos if isinstance(p, str)][:_MAX_PHOTOS]
        if isinstance(raw_photos, list)
        else []
    )

    status = await message.answer(SEO_SCANNING if photos else SEO_LOADING)

    attributes: SeoAttributes | None = None
    if photos:
        attributes = await _describe_photos(message, photos, description)
        if attributes is None:
            await message.answer(SEO_NO_VISION)

    request = _build_request(description, str(marketplace), advantages, attributes)
    if await launch_job_or_inline(
        state,
        SEO_JOB_TYPE,
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
            PROGRESS_STEPS.get(step, SEO_LOADING),
            edit_message_id=status.message_id,
        )

    report = await get_seo_service().generate(request, on_progress=on_progress)
    await state.clear()
    await sink.deliver(
        message.chat.id,
        render_seo_report(report),
        reply_markup=seo_result_keyboard(report),
        edit_message_id=status.message_id,
    )


def _build_request(
    description: str,
    marketplace: str,
    advantages: list[str],
    attributes: SeoAttributes | None,
) -> SeoRequest:
    if attributes is None:
        return SeoRequest(
            description=description,
            marketplace=Marketplace(marketplace),
            advantages=advantages,
        )
    return SeoRequest(
        description=description,
        marketplace=Marketplace(marketplace),
        advantages=advantages,
        name=attributes.name,
        category=attributes.category,
        brand=attributes.brand,
        key_features=attributes.key_features,
    )


register_media_hint(
    router,
    SeoTextScene.waiting_input,
    SeoTextScene.waiting_keywords,
    hint=SEO_INPUT_HINT,
)
