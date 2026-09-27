from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.core.database.session import get_session_factory
from src.modules.user.models import User
from src.modules.user.service import get_user_service


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Any,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        message = event.message
        if message is None or message.from_user is None:
            return await handler(event, data)

        async with get_session_factory()() as session:
            user = await get_user_service(session).get_or_create(message.from_user.id)
            data["user"] = user
            data["session"] = session
            return await handler(event, data)
