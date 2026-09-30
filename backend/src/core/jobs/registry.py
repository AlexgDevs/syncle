"""Job handler registry shared by composition roots (issue #8).

The core never imports business modules; the bot and the Taskiq worker
register their handlers here at startup, and the task executor looks
them up by job type.
"""

from src.core.jobs.base import JobHandler

_handlers: dict[str, JobHandler] = {}
_retries: dict[str, int] = {}


def register_job_handlers(
    handlers: dict[str, JobHandler], retries: dict[str, int] | None = None
) -> None:
    _handlers.update(handlers)
    if retries:
        _retries.update(retries)


def get_job_handler(job_type: str) -> JobHandler:
    try:
        return _handlers[job_type]
    except KeyError:
        raise KeyError(f"unknown job type: {job_type}") from None


def get_job_retries(job_type: str) -> int:
    return _retries.get(job_type, 0)
