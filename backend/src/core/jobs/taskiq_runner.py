"""Taskiq + Redis adapter for `BackgroundJobRunner` (issues #8, #38).

The broker and the ``run_analysis`` task live here so that both the
bot (submit path) and the worker (execution path) share a single task
definition. The broker itself is built lazily (``get_broker``), so
importing this module for ``TaskiqJobRunner`` does not touch settings
or construct taskiq objects. Job state (progress, terminal state,
result) is stored in a Redis hash; the bot's poller picks it up and
delivers the report through a `ResultSink`.
"""

import asyncio
import logging
import uuid
from functools import cache
from typing import Any

from taskiq_redis import ListQueueBroker

from src.core.jobs.base import (
    JobInfo,
    JobState,
    active_jobs_key,
    as_text,
    decode_payload,
    encode_payload,
    job_key,
)
from src.core.jobs.registry import get_job_handler, get_job_retries
from src.core.settings import get_settings

logger = logging.getLogger(__name__)

ANALYSIS_TASK_NAME = "run_analysis"
JOB_TTL_SECONDS = 24 * 60 * 60

_TERMINAL_STATES = frozenset({JobState.DONE, JobState.FAILED, JobState.CANCELLED})


@cache
def get_broker() -> ListQueueBroker:
    """Broker singleton with the ``run_analysis`` task registered.

    Job state/results live in our own Redis hash (see TaskiqJobRunner),
    so the broker needs no taskiq result backend. The worker exports the
    result as ``src.worker.app:broker``; the bot builds it on first submit.
    """
    broker = ListQueueBroker(get_settings().REDIS_URL)
    broker.register_task(run_analysis_task, task_name=ANALYSIS_TASK_NAME)
    return broker


class _RedisJobContext:
    """JobContext backed by the Redis job hash (worker side)."""

    def __init__(self, job_id: str) -> None:
        self._job_id = job_id
        self._cancelled = False

    async def progress(self, step: str) -> None:
        from src.core.redis import get_redis  # local: redis inited by worker startup

        redis = get_redis()
        state = await redis.hget(job_key(self._job_id), "state")
        if state == JobState.CANCELLED:
            self._cancelled = True
        if self._cancelled:
            raise asyncio.CancelledError(f"job {self._job_id} cancelled")
        await redis.hset(job_key(self._job_id), "progress", step)

    def cancelled(self) -> bool:
        return self._cancelled


async def _mark_cancelled(job_id: str) -> bool:
    from src.core.redis import get_redis

    redis = get_redis()
    state = await redis.hget(job_key(job_id), "state")
    if state is None or state in _TERMINAL_STATES:
        return False
    await redis.hset(job_key(job_id), "state", JobState.CANCELLED)
    return True


async def run_analysis_task(job_id: str) -> None:
    """Worker entry point: run the registered handler for the job.

    Registered on the broker by ``get_broker()`` (bot submit / worker start).
    """
    from src.core.redis import get_redis

    redis = get_redis()
    key = job_key(job_id)
    data = await redis.hgetall(key)
    if not data:
        logger.warning("job %s not found in redis", job_id)
        return
    job_type = as_text(data.get("job_type"))
    state = data.get("state")
    if state == JobState.CANCELLED:
        logger.info("job %s cancelled before start", job_id)
        return
    try:
        handler = get_job_handler(job_type)
    except KeyError:
        await redis.hset(
            key, mapping={"state": JobState.FAILED, "error": "unknown_job_type"}
        )
        logger.error("job %s has unknown type %r", job_id, job_type)
        return

    payload = decode_payload(as_text(data.get("payload")))
    context = _RedisJobContext(job_id)
    attempts = 1 + get_job_retries(job_type)
    await redis.hset(key, "state", JobState.RUNNING)
    for attempt in range(1, attempts + 1):
        try:
            result = await handler(payload, context)
        except asyncio.CancelledError:
            await redis.hset(key, "state", JobState.CANCELLED)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "job %s attempt %s/%s failed: %s",
                job_id,
                attempt,
                attempts,
                type(exc).__name__,
            )
            if attempt >= attempts:
                await redis.hset(
                    key,
                    mapping={"state": JobState.FAILED, "error": type(exc).__name__},
                )
                return
            continue
        current = await redis.hget(key, "state")
        if current == JobState.CANCELLED:
            return
        await redis.hset(
            key, mapping={"state": JobState.DONE, "result": result, "error": ""}
        )
        return


class TaskiqJobRunner:
    """Submits jobs to the Taskiq queue; state lives in Redis."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex
        await self._redis.hset(
            job_key(job_id),
            mapping={
                "id": job_id,
                "job_type": job_type,
                "state": JobState.PENDING,
                "payload": encode_payload(payload),
                "progress": "",
                "result": "",
                "error": "",
            },
        )
        await self._redis.expire(job_key(job_id), JOB_TTL_SECONDS)
        await self._redis.sadd(active_jobs_key(), job_id)
        task = get_broker().find_task(ANALYSIS_TASK_NAME)
        if task is None:
            raise RuntimeError(f"task {ANALYSIS_TASK_NAME!r} is not registered")
        await task.kiq(job_id)
        logger.info("job %s (%s) submitted", job_id, job_type)
        return job_id

    async def status(self, job_id: str) -> JobInfo | None:
        data = await self._redis.hgetall(job_key(job_id))
        if not data:
            return None
        try:
            state = JobState(as_text(data.get("state")) or JobState.PENDING)
        except ValueError:
            state = JobState.PENDING
        return JobInfo(
            id=job_id,
            job_type=as_text(data.get("job_type")),
            state=state,
            progress=as_text(data.get("progress")) or None,
            payload=decode_payload(as_text(data.get("payload"))),
            result=as_text(data.get("result")) or None,
            error=as_text(data.get("error")) or None,
        )

    async def cancel(self, job_id: str) -> bool:
        return await _mark_cancelled(job_id)
