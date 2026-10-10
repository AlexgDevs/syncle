import asyncio

from aiogram import Bot, Dispatcher, Router

from src.bot.errors import setup_error_handlers
from src.bot.handlers import setup_handlers
from src.bot.polling import start_job_poller
from src.bot.middlewares import UserMiddleware
from src.core.logging import setup_logging
from src.core.redis import close_redis, init_redis
from src.core.settings import get_settings


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.middleware(UserMiddleware())
    setup_error_handlers(dispatcher)

    router = Router(name="root")
    setup_handlers(router)
    dispatcher.include_router(router)
    return dispatcher


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    bot = Bot(token=settings.BOT_TOKEN)
    dispatcher = create_dispatcher()

    # Redis is required in every mode: the infographic stash reads/writes
    # it even when jobs run inline (#62)
    redis_client = await init_redis()
    poller = None
    if settings.JOBS_MODE == "taskiq":
        poller = await start_job_poller(bot)
    try:
        await dispatcher.start_polling(bot)
    finally:
        if poller is not None:
            await poller.stop()
        await close_redis(redis_client)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
