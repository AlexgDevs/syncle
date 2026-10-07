"""Result delivery abstraction (issue #9).

Both the fast (awaited) path and the background-job path deliver user
facing results through the same port; the bot provides an aiogram
adapter (`src.bot.delivery.AiogramResultSink`).
"""

from typing import Any, Protocol


class ResultSink(Protocol):
    async def deliver(
        self,
        chat_id: int,
        text: str,
        reply_markup: Any | None = None,
        edit_message_id: int | None = None,
    ) -> None:
        """Deliver `text` to `chat_id`.

        When `edit_message_id` is set, that message is edited in place
        (progress/status message); otherwise a new message is sent.
        """
        ...

    async def deliver_file(
        self,
        chat_id: int,
        caption: str,
        data: bytes,
        filename: str,
        reply_markup: Any | None = None,
    ) -> None:
        """Deliver `data` as a document with `caption` to `chat_id`.

        Used for reports that do not fit a single message (issue #43).
        """
        ...
