"""Delivers niche scan reports via ResultSink (issues #43, #44).

Short reports are delivered as a message (edited in place when a status
message id is given); long ones fall back to a Markdown file after a
short status note.
"""

import re
from typing import Any

from src.bot.renderers import NICHE_FILE_CAPTION, REPORT_LIMIT, render_niche_report
from src.bot.texts import DEEP_REPORT_READY
from src.core.results import ResultSink
from src.modules.analytics import NicheReport

_SLUG_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUG_SPACE_RE = re.compile(r"\s+")


def niche_report_filename(report: NicheReport) -> str:
    slug = _SLUG_RE.sub("", report.query).strip().lower()
    slug = _SLUG_SPACE_RE.sub("_", slug)[:40] or "report"
    return f"niche_{report.marketplace}_{slug}.md"


async def deliver_niche_report(
    sink: ResultSink,
    chat_id: int,
    report: NicheReport,
    status_message_id: int | None = None,
    reply_markup: Any | None = None,
) -> None:
    text = render_niche_report(report)
    full = render_niche_report(report, limit=None)
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
            DEEP_REPORT_READY,
            reply_markup=reply_markup,
            edit_message_id=status_message_id,
        )
    await sink.deliver_file(
        chat_id,
        NICHE_FILE_CAPTION.format(query=report.query),
        full.encode("utf-8"),
        niche_report_filename(report),
        reply_markup=reply_markup,
    )
