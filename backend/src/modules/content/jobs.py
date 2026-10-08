"""Background job handlers for the content module (issue #26).

Handlers receive the payload and a `JobContext`, and return the
serialized result (JSON). Step codes passed to `ctx.progress` are
mapped to RU text by the bot (`src.bot.texts.PROGRESS_STEPS`).
"""

from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.modules.content import get_seo_service
from src.modules.content.schemas import SeoRequest

SEO_JOB_TYPE = "seo_text"

SEO_RETRIES: dict[str, int] = {
    SEO_JOB_TYPE: 1,
}


async def seo_generate_job(payload: dict[str, Any], context: JobContext) -> str:
    """Generate a SEO block for one request (issues #24-#26).

    Delivery metadata (chat_id, status_message_id) stays in the payload;
    SeoRequest ignores it on validation.
    """
    request = SeoRequest.model_validate(payload)
    report = await get_seo_service().generate(request, on_progress=context.progress)
    return report.model_dump_json()


CONTENT_HANDLERS: dict[str, JobHandler] = {
    SEO_JOB_TYPE: seo_generate_job,
}


def register_content_jobs() -> None:
    """Register content handlers (called by the worker root)."""
    register_job_handlers(CONTENT_HANDLERS, SEO_RETRIES)
