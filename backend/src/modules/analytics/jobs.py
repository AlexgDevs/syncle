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
NICHE_SCAN_JOB_TYPE = "niche_scan"

ANALYSIS_RETRIES: dict[str, int] = {
    ANALYSIS_JOB_TYPE: 1,
    NICHE_SCAN_JOB_TYPE: 1,
}


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


async def niche_scan_job(payload: dict[str, Any], context: JobContext) -> str:
    """Deep niche scan (issue #43): search, aggregate, narrate.

    Progress calls double as cancellation checkpoints; a failing
    optional own card degrades inside the service instead of aborting.
    """
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("payload.query is required")
    marketplace = payload.get("marketplace")
    if marketplace not in ("wb", "ozon"):
        raise ValueError("payload.marketplace must be 'wb' or 'ozon'")
    own = payload.get("own")
    own_source = own if isinstance(own, str) and own.strip() else None

    service = get_analytics_service()
    report = await service.scan_niche(
        marketplace,
        query.strip(),
        own_source=own_source,
        on_progress=context.progress,
    )
    return report.model_dump_json()


ANALYSIS_HANDLERS: dict[str, JobHandler] = {
    ANALYSIS_JOB_TYPE: analysis_job,
    NICHE_SCAN_JOB_TYPE: niche_scan_job,
}


def register_analytics_jobs() -> None:
    """Register analytics handlers (called by bot and worker roots)."""
    register_job_handlers(ANALYSIS_HANDLERS, ANALYSIS_RETRIES)
