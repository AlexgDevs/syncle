from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message

from src.modules.analytics.parsers.source import parse_source


def is_valid_card_input(value: str) -> bool:
    _, parsed = parse_source(value)
    if parsed is None:
        return True
    return bool(parsed.netloc) and "." in parsed.netloc


async def safe_edit(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Edit message text, silently ignoring Telegram's "message is not modified"."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
