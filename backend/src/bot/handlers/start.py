from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.user.models import User

router = Router(name="start")


@router.message(Command("start"))
async def cmd_start(message: Message, user: User, session: AsyncSession) -> None:
    await message.answer(f"Привет! id={user.id} active={user.is_active}")
