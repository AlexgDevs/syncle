"""Background job abstraction (issue #8).

`BackgroundJobRunner` is the port; the project ships two adapters:

- `AsyncioJobRunner` — the asyncio-based reference implementation
  (in-process, fast path, per-job-type retry);
- `TaskiqJobRunner` — the Taskiq/Redis adapter for long analyses
  (separate worker process, job state lives in Redis).

Jobs report progress with step codes (EN); the bot maps codes to RU text.
"""

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from src.core.enums import JobState

__all__ = [
    "BackgroundJobRunner",
    "JobContext",
    "JobHandler",
    "JobInfo",
    "JobState",
    "active_jobs_key",
    "as_text",
    "decode_payload",
    "encode_payload",
    "job_key",
]


@dataclass
class JobInfo:
    id: str
    job_type: str
    state: JobState
    progress: str | None = None
    payload: dict[str, Any] | None = None
    result: str | None = None
    error: str | None = None


class JobContext(Protocol):
    """Execution context handed to a job handler."""

    async def progress(self, step: str) -> None:
        """Report a step code; also serves as a cancellation checkpoint."""
        ...

    def cancelled(self) -> bool:
        """True when the job was cancelled and must stop early."""
        ...


JobHandler = Callable[[dict[str, Any], JobContext], Awaitable[str]]
"""A job handler: payload in, serialized result (JSON string) out."""


class BackgroundJobRunner(Protocol):
    async def submit(self, job_type: str, payload: dict[str, Any]) -> str:
        """Enqueue a job; returns the job id."""
        ...

    async def status(self, job_id: str) -> JobInfo | None:
        """Current job info (progress and terminal state) by id."""
        ...

    async def cancel(self, job_id: str) -> bool:
        """Ask a job to stop; True when cancellation was registered."""
        ...


def job_key(job_id: str) -> str:
    return f"syncle:job:{job_id}"


def active_jobs_key() -> str:
    return "syncle:jobs:active"


def encode_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def decode_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def as_text(value: bytes | str | None) -> str:
    """Normalize Redis string values (client uses decode_responses=True)."""
    if value is None:
        return ""
    return value.decode() if isinstance(value, bytes) else value
