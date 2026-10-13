"""Background job handlers for the legal module (issue #60).

The business scan (#59) runs as a background job: the light payload
carries sources/free text plus delivery metadata, seller documents
travel through the Redis stash. The quick card scan (scene A) is a
separate rules-only job — no LLM on that path. Step codes passed to
``ctx.progress`` are mapped to RU text by the bot
(``src.bot.texts.PROGRESS_STEPS``).
"""

from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.core.stash import load_documents
from src.modules.legal import get_legal_service
from src.modules.legal.fetch import fetch_card
from src.modules.legal.history import save_scan
from src.modules.legal.schemas import LegalCardPayload, LegalJobPayload
from src.modules.legal.service import SCAN_PROGRESS_STEP

LEGAL_JOB_TYPE = "legal_scan"
LEGAL_CARD_JOB_TYPE = "legal_card_scan"

LEGAL_RETRIES: dict[str, int] = {
    LEGAL_JOB_TYPE: 1,
    LEGAL_CARD_JOB_TYPE: 1,
}


async def legal_scan_job(payload: dict[str, Any], context: JobContext) -> str:
    """Run the business-wide compliance scan (issues #59/#60).

    Documents are read back from the stash by chat_id; the payload
    stays JSON-light for taskiq.
    """
    request = LegalJobPayload.model_validate(payload)
    documents = await load_documents(request.chat_id)
    report = await get_legal_service().scan_business(
        request.sources,
        request.free_text,
        documents,
        on_progress=context.progress,
    )
    await save_scan(request.user_id, report, chat_id=request.chat_id)
    return report.model_dump_json()


async def legal_card_scan_job(payload: dict[str, Any], context: JobContext) -> str:
    """Quick card scan: fetch + deterministic rules only (scene A, #60)."""
    request = LegalCardPayload.model_validate(payload)
    await context.progress(SCAN_PROGRESS_STEP)
    card = await fetch_card(request.source)
    report = get_legal_service().scan_card(
        card.title or "", card.description or "", source=request.source
    )
    await save_scan(request.user_id, report, chat_id=request.chat_id, scope="card")
    return report.model_dump_json()


LEGAL_HANDLERS: dict[str, JobHandler] = {
    LEGAL_JOB_TYPE: legal_scan_job,
    LEGAL_CARD_JOB_TYPE: legal_card_scan_job,
}


def register_legal_jobs() -> None:
    """Register legal handlers (called by the worker root)."""
    register_job_handlers(LEGAL_HANDLERS, LEGAL_RETRIES)
