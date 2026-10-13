"""Legal scanner scenes (M6, #60): quick card scan and business audit.

Both scenes run as taskiq jobs with an inline fallback: the quick card
scan submits ``legal_card_scan`` (deterministic rules only, no LLM) and
the business audit collects card sources, optional free text and
documents, then submits ``legal_scan``; documents travel via the Redis
stash.
"""

import base64
import io
import logging
from uuid import UUID

from aiogram import F, Router
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
    legal_audit_docs_setup,
    legal_audit_skip_setup,
    legal_result_keyboard,
)
from src.bot.renderers import (
    render_legal_business_report,
    render_legal_card_report,
)
from src.bot.texts import (
    LEGAL_AUDIT_DOCS_PROMPT,
    LEGAL_AUDIT_LOADING,
    LEGAL_AUDIT_PROMPT,
    LEGAL_AUDIT_TEXT_PROMPT,
    LEGAL_CARD_CAP_REACHED,
    LEGAL_CARD_DONE,
    LEGAL_CARD_PROMPT,
    LEGAL_DOC_CAP,
    LEGAL_DOC_FAILED,
    LEGAL_DOC_RECEIVED,
    LEGAL_DOC_UNSUPPORTED,
    LEGAL_INPUT_HINT,
    LEGAL_LOADING,
    LEGAL_NO_INPUT,
    LEGAL_SCAN_FAILED,
    LEGAL_SOURCE_ADDED,
    LEGAL_TEXT_SHORT,
    PROGRESS_STEPS,
)
from src.bot.utils import is_valid_card_input, safe_edit
from src.core.errors import SyncleError
from src.core.settings import get_settings
from src.core.stash import stash_documents
from src.modules.legal import get_legal_service
from src.modules.legal.fetch import fetch_card
from src.modules.legal.history import save_scan
from src.modules.legal.jobs import LEGAL_CARD_JOB_TYPE, LEGAL_JOB_TYPE
from src.modules.legal.schemas import LegalCardPayload, LegalJobPayload
from src.modules.user.models import User

logger = logging.getLogger(__name__)
router = Router(name="legal")

_AUDIT_SKIP = "scene:legal:audit:skip"
_AUDIT_DONE = "scene:legal:audit:done"
_MIN_TEXT_LEN = 10
_DOC_SUFFIXES = (".pdf", ".docx", ".xlsx", ".csv")

LEGAL_AUDIT_DOCS_HINT = (
    "Пришлите документ файлом (PDF, DOCX, XLSX, CSV) или нажмите «Готово»."
)


class LegalCardScene(StatesGroup):
    waiting_link = State()


class LegalAuditScene(StatesGroup):
    waiting_sources = State()
    waiting_text = State()
    waiting_docs = State()


# --- quick card scan (deterministic only, no LLM) ---


@router.callback_query(F.data == "scene:legal:card")
async def start_card_scan(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(LegalCardScene.waiting_link)
    await safe_edit(callback.message, LEGAL_CARD_PROMPT, back_menu())
    await callback.answer()


@router.message(LegalCardScene.waiting_link, F.text)
async def handle_card_link(message: Message, state: FSMContext, user: User) -> None:
    value = (message.text or "").strip()
    if not is_valid_card_input(value):
        await message.answer(LEGAL_INPUT_HINT)
        return
    status = await message.answer(LEGAL_LOADING)
    payload = LegalCardPayload(
        user_id=user.id,
        chat_id=message.chat.id,
        status_message_id=status.message_id,
        source=value,
    )
    if await launch_job_or_inline(
        state, LEGAL_CARD_JOB_TYPE, payload.model_dump(mode="json")
    ):
        return
    # inline fallback: same steps as legal_card_scan_job
    try:
        card = await fetch_card(value)
        report = get_legal_service().scan_card(
            card.title or "", card.description or "", source=value
        )
    except SyncleError as exc:
        await safe_edit(status, describe_error(exc))
        return
    except Exception:  # noqa: BLE001
        logger.exception("quick legal scan failed")
        await safe_edit(status, LEGAL_SCAN_FAILED)
        return
    await save_scan(user.id, report, chat_id=message.chat.id, scope="card")
    await state.clear()
    await safe_edit(
        status,
        f"{LEGAL_CARD_DONE}\n\n{render_legal_card_report(report)}",
        back_menu(),
    )


register_media_hint(router, LegalCardScene.waiting_link, hint=LEGAL_INPUT_HINT)


# --- business audit (#60) ---


@router.callback_query(F.data == "scene:legal:audit")
async def start_audit(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.clear()
    await state.set_state(LegalAuditScene.waiting_sources)
    await state.update_data(sources=[], documents=[], free_text="")
    await safe_edit(callback.message, LEGAL_AUDIT_PROMPT, legal_audit_skip_setup())
    await callback.answer()


@router.message(LegalAuditScene.waiting_sources, F.text)
async def handle_audit_source(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not is_valid_card_input(value):
        await message.answer(LEGAL_INPUT_HINT)
        return
    data = await state.get_data()
    sources = [item for item in data.get("sources", []) if isinstance(item, str)]
    cfg = get_settings()
    if value in sources:
        await message.answer(
            LEGAL_SOURCE_ADDED.format(source=value, count=len(sources))
        )
        return
    if len(sources) >= cfg.LEGAL_CARD_CAP:
        await message.answer(LEGAL_CARD_CAP_REACHED.format(cap=cfg.LEGAL_CARD_CAP))
        return
    sources.append(value)
    await state.update_data(sources=sources)
    await message.answer(
        LEGAL_SOURCE_ADDED.format(source=value, count=len(sources)),
        reply_markup=legal_audit_skip_setup(),
    )


@router.callback_query(F.data == _AUDIT_SKIP)
async def audit_skip(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    if current == LegalAuditScene.waiting_sources.state:
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        await state.set_state(LegalAuditScene.waiting_text)
        await safe_edit(
            callback.message, LEGAL_AUDIT_TEXT_PROMPT, legal_audit_skip_setup()
        )
        await callback.answer()
        return
    if current == LegalAuditScene.waiting_text.state:
        if not isinstance(callback.message, Message):
            await callback.answer()
            return
        cfg = get_settings()
        await state.set_state(LegalAuditScene.waiting_docs)
        await safe_edit(
            callback.message,
            LEGAL_AUDIT_DOCS_PROMPT.format(cap=cfg.LEGAL_DOCUMENT_CAP),
            legal_audit_docs_setup(),
        )
        await callback.answer()
        return
    await callback.answer()


@router.message(LegalAuditScene.waiting_text, F.text)
async def handle_audit_text(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if len(value) < _MIN_TEXT_LEN:
        await message.answer(LEGAL_TEXT_SHORT)
        return
    await state.update_data(free_text=value)
    cfg = get_settings()
    await state.set_state(LegalAuditScene.waiting_docs)
    await message.answer(
        LEGAL_AUDIT_DOCS_PROMPT.format(cap=cfg.LEGAL_DOCUMENT_CAP),
        reply_markup=legal_audit_docs_setup(),
    )


def _doc_filename(message: Message) -> str:
    if message.document is None or not message.document.file_name:
        return "document"
    return message.document.file_name


def _doc_supported(filename: str) -> bool:
    lowered = filename.lower()
    return any(lowered.endswith(suffix) for suffix in _DOC_SUFFIXES)


@router.message(LegalAuditScene.waiting_docs, F.document)
async def handle_audit_document(message: Message, state: FSMContext) -> None:
    filename = _doc_filename(message)
    if not _doc_supported(filename):
        await message.answer(LEGAL_DOC_UNSUPPORTED.format(filename=filename))
        return
    if message.document is None or message.bot is None:
        await message.answer(LEGAL_DOC_FAILED.format(filename=filename))
        return
    data = await state.get_data()
    documents = [item for item in data.get("documents", []) if isinstance(item, dict)]
    cfg = get_settings()
    if len(documents) >= cfg.LEGAL_DOCUMENT_CAP:
        await message.answer(LEGAL_DOC_CAP.format(cap=cfg.LEGAL_DOCUMENT_CAP))
        return
    try:
        file = await message.bot.get_file(message.document.file_id)
        buffer = io.BytesIO()
        await message.bot.download(file, destination=buffer)
        downloaded = buffer.getvalue()
    except Exception:  # noqa: BLE001
        logger.warning("legal document download failed", exc_info=True)
        await message.answer(LEGAL_DOC_FAILED.format(filename=filename))
        return
    if not downloaded:
        await message.answer(LEGAL_DOC_FAILED.format(filename=filename))
        return
    documents.append(
        {
            "file_id": message.document.file_id,
            "filename": filename,
            "data_b64": base64.b64encode(downloaded).decode("ascii"),
        }
    )
    await state.update_data(documents=documents)
    await message.answer(
        LEGAL_DOC_RECEIVED.format(filename=filename, count=len(documents)),
        reply_markup=legal_audit_docs_setup(),
    )


@router.message(LegalAuditScene.waiting_docs, F.text)
async def handle_audit_docs_text(message: Message) -> None:
    await message.answer(LEGAL_AUDIT_DOCS_HINT, reply_markup=legal_audit_docs_setup())


@router.callback_query(F.data == _AUDIT_DONE)
async def audit_done(callback: CallbackQuery, state: FSMContext, user: User) -> None:
    if not await require_state(state, LegalAuditScene.waiting_docs, callback):
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    data = await state.get_data()
    sources = [item for item in data.get("sources", []) if isinstance(item, str)]
    free_text_raw = data.get("free_text")
    free_text = free_text_raw.strip() if isinstance(free_text_raw, str) else ""
    documents = _decode_documents(data)
    if not sources and not free_text and not documents:
        await state.clear()
        await safe_edit(callback.message, LEGAL_NO_INPUT, back_menu())
        await callback.answer()
        return
    # Ack before the long scan: callbacks expire while we wait.
    await callback.answer()
    await stash_documents(callback.message.chat.id, documents)
    await _launch(callback.message, state, user.id, sources, free_text)


def _decode_documents(data: dict[str, object]) -> list[tuple[str, bytes]]:
    raw = data.get("documents")
    if not isinstance(raw, list):
        return []
    documents: list[tuple[str, bytes]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        encoded = item.get("data_b64")
        if not isinstance(filename, str) or not isinstance(encoded, str):
            continue
        try:
            documents.append((filename, base64.b64decode(encoded)))
        except ValueError:
            logger.warning("stashed document unreadable; skipping")
    return documents


async def _launch(
    message: Message,
    state: FSMContext,
    user_id: UUID,
    sources: list[str],
    free_text: str,
) -> None:
    status = await message.answer(LEGAL_AUDIT_LOADING)
    payload = LegalJobPayload(
        user_id=user_id,
        chat_id=message.chat.id,
        status_message_id=status.message_id,
        sources=sources,
        free_text=free_text,
    )
    if await launch_job_or_inline(
        state, LEGAL_JOB_TYPE, payload.model_dump(mode="json")
    ):
        return
    sink = result_sink(message)

    async def on_progress(step: str) -> None:
        await sink.deliver(
            message.chat.id,
            PROGRESS_STEPS.get(step, LEGAL_AUDIT_LOADING),
            edit_message_id=status.message_id,
        )

    report = await get_legal_service().scan_business(
        sources, free_text, on_progress=on_progress
    )
    await save_scan(user_id, report, chat_id=message.chat.id)
    await state.clear()
    await sink.deliver(
        message.chat.id,
        render_legal_business_report(report),
        reply_markup=legal_result_keyboard(report),
        edit_message_id=status.message_id,
    )


register_media_hint(router, LegalAuditScene.waiting_sources, hint=LEGAL_INPUT_HINT)
register_media_hint(router, LegalAuditScene.waiting_text, hint=LEGAL_TEXT_SHORT)
register_media_hint(router, LegalAuditScene.waiting_docs, hint=LEGAL_AUDIT_DOCS_HINT)
