from aiogram import Router

from src.bot.handlers.deep_scan import router as deep_scan_router
from src.bot.handlers.express_analysis import router as express_router
from src.bot.handlers.menu import router as menu_router
from src.bot.handlers.seo_text import router as seo_router
from src.bot.handlers.start import router as start_router


def setup_handlers(router: Router) -> None:
    router.include_router(start_router)
    router.include_router(menu_router)
    router.include_router(express_router)
    router.include_router(deep_scan_router)
    router.include_router(seo_router)
