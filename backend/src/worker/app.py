"""Taskiq worker application (issues #8, #38).

Run from `backend/`:

    uv run taskiq worker src.worker.app:broker

Registers business handlers and Redis lifecycle hooks; `get_broker()`
lazily builds the broker with the shared `run_analysis` task, which the
bot also uses for submits via `src.core.jobs`.
"""

from taskiq import TaskiqEvents

from src.core.jobs.taskiq_runner import get_broker
from src.core.redis import close_redis, init_redis
from src.core.redis.client import get_redis
from src.modules.analytics.jobs import register_analytics_jobs

register_analytics_jobs()

broker = get_broker()


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def on_startup(state: object) -> None:
    await init_redis()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def on_shutdown(state: object) -> None:
    await close_redis(get_redis())


__all__ = ["broker"]
