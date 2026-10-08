"""Adapter-level error handling for the bot.

Maps domain errors (src.core.errors.SyncleError hierarchy) to RU texts and
delivers them to the user; unexpected exceptions are logged with a traceback.
The future API adapter implements the same contract as JSON responses.
"""

import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import CallbackQuery, ErrorEvent, Message, Update

from src.bot.texts import (
    CARD_NOT_FOUND,
    GENERIC_ERROR,
    LLM_RATE_LIMIT_TEXT,
    LLM_TIMEOUT_TEXT,
    LLM_UNAVAILABLE_TEXT,
    NICHE_SEARCH_FAILED,
    OZON_BROWSER_UNAVAILABLE,
    PARSE_FAILED,
    REVIEWS_FAILED,
    REVIEWS_FETCH_FAILED,
    SEO_FAILED,
    UNSUPPORTED_MARKETPLACE,
)
from src.core.errors import SyncleError
from src.core.llm import LLMRateLimitError, LLMTimeoutError, LLMUnavailableError
from src.modules.analytics.errors import (
    CardNotFoundError,
    CardParseError,
    NicheSearchError,
    OzonBrowserError,
    UnsupportedMarketplaceError,
)
from src.modules.content.errors import SeoGenerationError
from src.modules.reviews import ReviewAnalysisError, ReviewsFetchError

logger = logging.getLogger(__name__)


def describe_error(exc: Exception) -> str:
    if isinstance(exc, UnsupportedMarketplaceError):
        return UNSUPPORTED_MARKETPLACE.format(name=exc.marketplace.title())
    if isinstance(exc, OzonBrowserError):
        return OZON_BROWSER_UNAVAILABLE
    if isinstance(exc, CardNotFoundError):
        return CARD_NOT_FOUND
    if isinstance(exc, CardParseError):
        return PARSE_FAILED
    if isinstance(exc, NicheSearchError):
        return NICHE_SEARCH_FAILED
    if isinstance(exc, SeoGenerationError):
        return SEO_FAILED
    if isinstance(exc, ReviewsFetchError):
        return REVIEWS_FETCH_FAILED
    if isinstance(exc, ReviewAnalysisError):
        return REVIEWS_FAILED
    if isinstance(exc, LLMTimeoutError):
        return LLM_TIMEOUT_TEXT
    if isinstance(exc, LLMRateLimitError):
        return LLM_RATE_LIMIT_TEXT
    if isinstance(exc, LLMUnavailableError):
        return LLM_UNAVAILABLE_TEXT
    return GENERIC_ERROR


def _chat_id(update: Update) -> int | None:
    event = update.event
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery):
        if isinstance(event.message, Message):
            return event.message.chat.id
        return event.from_user.id
    return None


async def _send(bot: Bot, chat_id: int | None, text: str) -> None:
    if chat_id is None:
        return
    try:
        await bot.send_message(chat_id, text)
    except TelegramAPIError as exc:
        logger.error("Failed to deliver error message: %s", type(exc).__name__)


def setup_error_handlers(dispatcher: Dispatcher) -> None:
    @dispatcher.error(ExceptionTypeFilter(SyncleError))
    async def on_domain_error(event: ErrorEvent, bot: Bot) -> bool:
        exc = event.exception
        logger.warning("Domain error: %s: %s", type(exc).__name__, str(exc))
        await _send(bot, _chat_id(event.update), describe_error(exc))
        return True

    @dispatcher.error()
    async def on_unexpected_error(event: ErrorEvent, bot: Bot) -> bool:
        exc = event.exception
        logger.error("Unhandled error while processing update", exc_info=exc)
        await _send(bot, _chat_id(event.update), GENERIC_ERROR)
        return True
