"""Background job handlers for the reviews module (issue #31).

Handlers receive the payload and a `JobContext`, and return the
serialized result (JSON). Step codes passed to `ctx.progress` are
mapped to RU text by the bot (`src.bot.texts.PROGRESS_STEPS`).
"""

from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.modules.reviews import ReviewAnalysisRequest, get_reviews_service

REVIEWS_JOB_TYPE = "reviews_analysis"

REVIEWS_RETRIES: dict[str, int] = {
    REVIEWS_JOB_TYPE: 1,
}


async def reviews_analysis_job(payload: dict[str, Any], context: JobContext) -> str:
    """Run tag/finding analysis over the selected reviews (issues #28-#32).

    Delivery metadata (chat_id, status_message_id) stays in the payload;
    ReviewAnalysisRequest ignores it on validation.
    """
    request = ReviewAnalysisRequest.model_validate(payload)
    report = await get_reviews_service().analyze(request, on_progress=context.progress)
    return report.model_dump_json()


REVIEWS_HANDLERS: dict[str, JobHandler] = {
    REVIEWS_JOB_TYPE: reviews_analysis_job,
}


def register_reviews_jobs() -> None:
    """Register reviews handlers (called by the worker root)."""
    register_job_handlers(REVIEWS_HANDLERS, REVIEWS_RETRIES)
