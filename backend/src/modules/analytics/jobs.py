"""Background job handlers for the analytics module (issues #8, #38).

Handlers receive the payload and a `JobContext`, and return the
serialized report (JSON). Step codes passed to `ctx.progress` are
mapped to RU text by the bot (`src.bot.texts.PROGRESS_STEPS`).
"""

from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.modules.analytics import get_analytics_service

ANALYSIS_JOB_TYPE = "analysis"

ANALYSIS_RETRIES: dict[str, int] = {ANALYSIS_JOB_TYPE: 1}


async def analysis_job(payload: dict[str, Any], context: JobContext) -> str:
    rival = payload.get("rival")
    if not isinstance(rival, str) or not rival.strip():
        raise ValueError("payload.rival is required")
    own = payload.get("own")
    own_source = own if isinstance(own, str) and own.strip() else None

    service = get_analytics_service()
    report = await service.compare_cards(
        own_source, rival, on_progress=context.progress
    )
    return report.model_dump_json()


ANALYSIS_HANDLERS: dict[str, JobHandler] = {ANALYSIS_JOB_TYPE: analysis_job}


def register_analytics_jobs() -> None:
    """Register analytics handlers (called by bot and worker roots)."""
    register_job_handlers(ANALYSIS_HANDLERS, ANALYSIS_RETRIES)
