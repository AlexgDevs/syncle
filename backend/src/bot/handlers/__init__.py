from aiogram import Router

from src.bot.handlers.start import router as start_router


def setup_handlers(router: Router) -> None:
    router.include_router(start_router)
