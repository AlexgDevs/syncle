"""Background job handler for the settlement report analysis (issue #52).

Light JSON payload carries delivery metadata; the report file travels
through the Redis stash. Step codes passed to ``ctx.progress`` are
mapped to RU text by the bot (``src.bot.texts.PROGRESS_STEPS``).
"""

from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.core.stash import load_report
from src.modules.finance.errors import ReportParseError
from src.modules.finance.schemas import FinanceReportPayload
from src.modules.finance.service import get_finance_service

FINANCE_JOB_TYPE = "finance_report"

FINANCE_RETRIES: dict[str, int] = {
    FINANCE_JOB_TYPE: 1,
}


async def finance_report_job(payload: dict[str, Any], context: JobContext) -> str:
    """Analyze an uploaded settlement report (scene B, #49-#52).

    The file is read back from the stash by chat_id; the payload stays
    JSON-light for taskiq. Raises ``ReportParseError`` on broken files —
    the poller maps it to a RU message.
    """
    request = FinanceReportPayload.model_validate(payload)
    entry = await load_report(request.chat_id)
    if entry is None:
        raise ReportParseError("stashed report is missing or expired")
    filename, data = entry
    analysis = await get_finance_service().analyze(
        data, filename=filename, on_progress=context.progress
    )
    return analysis.model_dump_json()


FINANCE_HANDLERS: dict[str, JobHandler] = {
    FINANCE_JOB_TYPE: finance_report_job,
}


def register_finance_jobs() -> None:
    """Register finance handlers (called by the worker root)."""
    register_job_handlers(FINANCE_HANDLERS, FINANCE_RETRIES)
