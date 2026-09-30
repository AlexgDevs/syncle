"""Taskiq worker application (issues #8, #38).

Run from `backend/`:

    uv run taskiq worker src.worker.app:broker

Registers business handlers and Redis lifecycle hooks; `broker` and the
`run_analysis` task are shared with the bot via `src.core.jobs`.
"""

from taskiq import TaskiqEvents

from src.core.jobs.taskiq_runner import broker
from src.core.redis import close_redis, init_redis
from src.core.redis.client import get_redis
from src.modules.analytics.jobs import register_analytics_jobs

register_analytics_jobs()


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def on_startup(state: object) -> None:
    await init_redis()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def on_shutdown(state: object) -> None:
    await close_redis(get_redis())


__all__ = ["broker"]
