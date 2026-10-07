"""Background job handlers for the analytics module (issues #8, #38).

Handlers receive the payload and a `JobContext`, and return the
serialized report (JSON). Step codes passed to `ctx.progress` are
mapped to RU text by the bot (`src.bot.texts.PROGRESS_STEPS`).
"""

from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.modules.analytics import get_analytics_service
from src.modules.analytics.enums import MARKETPLACES

ANALYSIS_JOB_TYPE = "analysis"
NICHE_SCAN_JOB_TYPE = "niche_scan"

ANALYSIS_RETRIES: dict[str, int] = {
    ANALYSIS_JOB_TYPE: 1,
    NICHE_SCAN_JOB_TYPE: 1,
}


def require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload.{key} is required")
    return value.strip()


def optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


async def analysis_job(payload: dict[str, Any], context: JobContext) -> str:
    rival = require_str(payload, "rival")
    own_source = optional_str(payload, "own")

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
    query = require_str(payload, "query")
    marketplace = payload.get("marketplace")
    if marketplace not in MARKETPLACES:
        raise ValueError("payload.marketplace must be 'wb' or 'ozon'")
    own_source = optional_str(payload, "own")

    service = get_analytics_service()
    report = await service.scan_niche(
        str(marketplace),
        query,
        own_source=own_source,
        on_progress=context.progress,
    )
    return report.model_dump_json()


ANALYSIS_HANDLERS: dict[str, JobHandler] = {
    ANALYSIS_JOB_TYPE: analysis_job,
    NICHE_SCAN_JOB_TYPE: niche_scan_job,
}


def register_analytics_jobs() -> None:
    """Register analytics handlers (called by the worker root)."""
    register_job_handlers(ANALYSIS_HANDLERS, ANALYSIS_RETRIES)
