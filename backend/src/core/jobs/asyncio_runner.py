"""Asyncio-based reference implementation of `BackgroundJobRunner` (#8).

Runs jobs in-process with `asyncio.create_task`, keeps job state in
memory, supports cancellation via cooperative checkpoints and a
configurable retry count per job type. Used for the fast (awaited)
path and tests; the Taskiq adapter is the long-path implementation.
"""

import asyncio
import logging
import uuid
from typing import Any

from src.core.jobs.base import (
    JobContext,
    JobHandler,
    JobInfo,
    JobState,
)

logger = logging.getLogger(__name__)


class _Context:
    def __init__(self, runner: "AsyncioJobRunner", job_id: str) -> None:
        self._runner = runner
        self._job_id = job_id

    async def progress(self, step: str) -> None:
        info = self._runner._jobs.get(self._job_id)
        if info is not None:
            info.progress = step
        if self.cancelled():
            raise asyncio.CancelledError(f"job {self._job_id} cancelled")

    def cancelled(self) -> bool:
        info = self._runner._jobs.get(self._job_id)
        return info is not None and info.state == JobState.CANCELLED


class AsyncioJobRunner:
    """In-memory job runner; state is lost on process restart."""

    def __init__(
        self,
        handlers: dict[str, JobHandler],
        retries: dict[str, int] | None = None,
    ) -> None:
        self._handlers = handlers
        self._retries = retries or {}
        self._jobs: dict[str, JobInfo] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        if job_type not in self._handlers:
            raise KeyError(f"unknown job type: {job_type}")
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = JobInfo(
            id=job_id, job_type=job_type, state=JobState.PENDING, payload=payload
        )
        self._tasks[job_id] = asyncio.create_task(self._run(job_id))
        return job_id

    async def status(self, job_id: str) -> JobInfo | None:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> bool:
        info = self._jobs.get(job_id)
        if info is None or info.state in {
            JobState.DONE,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            return False
        info.state = JobState.CANCELLED
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return True

    async def _run(self, job_id: str) -> None:
        info = self._jobs[job_id]
        handler = self._handlers[info.job_type]
        attempts = 1 + self._retries.get(info.job_type, 0)
        info.state = JobState.RUNNING
        context = _Context(self, job_id)
        for attempt in range(1, attempts + 1):
            try:
                result = await handler(info.payload or {}, context)
            except asyncio.CancelledError:
                info.state = JobState.CANCELLED
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
                    info.state = JobState.FAILED
                    info.error = type(exc).__name__
                    return
                info.progress = None
                continue
            if info.state == JobState.CANCELLED:
                return
            info.result = result
            info.state = JobState.DONE
            return
