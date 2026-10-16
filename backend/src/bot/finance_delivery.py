"""Delivers settlement report analyses via ResultSink (M5, issue #52).

Short analyses are delivered as a message (edited in place when a status
message id is given); long ones fall back to a Markdown file after a
short status note — same pattern as the niche report.
"""

import re
from typing import Any

from src.bot.renderers import (
    FIN_FILE_CAPTION,
    REPORT_LIMIT,
    render_report_analysis,
)
from src.bot.texts import FIN_REPORT_FILE_READY
from src.core.results import ResultSink
from src.modules.finance import ReportAnalysis

_SLUG_RE = re.compile(r"[^\w-]+", re.UNICODE)


def finance_report_filename(analysis: ReportAnalysis) -> str:
    stem = analysis.filename.rsplit("/", 1)[-1]
    stem = stem.rsplit(".", 1)[0]
    slug = _SLUG_RE.sub("_", stem).strip("_")[:40]
    return f"finance_{slug or 'report'}.md"


async def deliver_report_analysis(
    sink: ResultSink,
    chat_id: int,
    analysis: ReportAnalysis,
    status_message_id: int | None = None,
    reply_markup: Any | None = None,
) -> None:
    text = render_report_analysis(analysis)
    full = render_report_analysis(analysis, limit=None)
    if len(full) <= REPORT_LIMIT:
        await sink.deliver(
            chat_id,
            text,
            reply_markup=reply_markup,
            edit_message_id=status_message_id,
        )
        return
    if status_message_id is not None:
        await sink.deliver(
            chat_id,
            FIN_REPORT_FILE_READY,
            reply_markup=reply_markup,
            edit_message_id=status_message_id,
        )
    await sink.deliver_file(
        chat_id,
        FIN_FILE_CAPTION.format(filename=analysis.filename),
        full.encode("utf-8"),
        finance_report_filename(analysis),
        reply_markup=reply_markup,
    )
