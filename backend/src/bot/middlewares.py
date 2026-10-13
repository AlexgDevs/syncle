from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.core.database.session import get_session_factory
from src.modules.user.models import User
from src.modules.user.service import get_user_service


class UserMiddleware(BaseMiddleware):
    """Resolve (or create) the domain user for messages and callbacks.

    Callback queries carry no ``Update.message``, so they were skipped
    before M6: scenes launched from inline keyboards could not read
    ``data["user"]`` (needed e.g. for legal scan history keys).
    """

    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        telegram_id = _telegram_id(event)
        if telegram_id is None:
            return await handler(event, data)

        async with get_session_factory()() as session:
            user = await get_user_service(session).get_or_create(telegram_id)
            data["user"] = user
            data["session"] = session
            return await handler(event, data)


def _telegram_id(event: Update) -> int | None:
    callback = event.callback_query
    if callback is not None and callback.from_user is not None:
        return callback.from_user.id
    message = event.message
    if message is not None and message.from_user is not None:
        return message.from_user.id
    return None
