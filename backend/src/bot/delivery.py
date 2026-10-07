"""Aiogram adapter for `ResultSink` (issue #9)."""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup


class AiogramResultSink:
    """Delivers report text by editing the status message or sending new."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def deliver(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        edit_message_id: int | None = None,
    ) -> None:
        if edit_message_id is not None:
            try:
                await self._bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=edit_message_id,
                    reply_markup=reply_markup,
                )
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc):
                    return
                # stale or uneditable status message: fall back to a new one
        await self._bot.send_message(chat_id, text, reply_markup=reply_markup)

    async def deliver_file(
        self,
        chat_id: int,
        caption: str,
        data: bytes,
        filename: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        await self._bot.send_document(
            chat_id,
            BufferedInputFile(data, filename=filename),
            caption=caption,
            reply_markup=reply_markup,
        )
