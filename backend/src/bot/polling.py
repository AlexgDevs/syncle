"""Background job wiring for the bot (issues #8, #9, #38).

`JobPoller` is a background loop that watches jobs submitted through
`TaskiqJobRunner`, updates their status message with progress step
codes, and delivers terminal results via `ResultSink`.
"""

import asyncio
import base64
import logging
from functools import lru_cache

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from src.bot.delivery import AiogramResultSink
from src.bot.keyboards.inline import (
    back_menu,
    infographic_variants,
    reviews_result_keyboard,
    seo_result_keyboard,
)
from src.bot.niche_delivery import deliver_niche_report
from src.bot.photos import download_photos
from src.bot.renderers import (
    render_analysis_report,
    render_infographic_caption,
    render_reviews_report,
    render_seo_report,
)
from src.bot.texts import (
    ANALYSIS_LOADING,
    INFO_FAILED,
    JOB_CANCELLED,
    JOB_FAILED,
    PROGRESS_STEPS,
)
from src.core.jobs.base import JobInfo, JobState, active_jobs_key, as_text, job_key
from src.core.jobs.taskiq_runner import TaskiqJobRunner
from src.core.redis import get_redis
from src.core.results import ResultSink
from src.core.settings import get_settings
from src.core.stash import stash_seo
from src.modules.analytics.jobs import NICHE_SCAN_JOB_TYPE
from src.modules.analytics.schemas import AnalysisReport, NicheReport
from src.modules.content import SeoText
from src.modules.content.jobs import SEO_JOB_TYPE
from src.modules.infographics import RenderedArtwork
from src.modules.infographics.jobs import INFOGRAPHICS_JOB_TYPE
from src.modules.reviews import ReviewReport
from src.modules.reviews.jobs import REVIEWS_JOB_TYPE

logger = logging.getLogger(__name__)


@lru_cache
def get_job_runner() -> TaskiqJobRunner:
    return TaskiqJobRunner(get_redis())


class JobPoller:
    def __init__(
        self,
        runner: TaskiqJobRunner,
        sink: ResultSink,
        interval: float | None = None,
        bot: Bot | None = None,
    ) -> None:
        self._runner = runner
        self._sink = sink
        self._bot = bot  # downloads seller photos for the SEO stash (#62)
        self._interval = interval or get_settings().JOBS_POLL_INTERVAL
        self._task: asyncio.Task[None] | None = None
        self._progress_seen: dict[str, str] = {}

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info("job poller started (interval=%.1fs)", self._interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("job poller tick failed")

    async def _tick(self) -> None:
        redis = get_redis()
        job_ids = await redis.smembers(active_jobs_key())
        for raw_job_id in job_ids:
            job_id = as_text(raw_job_id)
            info = await self._runner.status(job_id)
            if info is None:
                await self._cleanup(job_id)
                continue
            if info.state in (JobState.PENDING, JobState.RUNNING):
                await self._update_progress(info)
            elif info.state == JobState.DONE:
                await self._deliver_result(info)
                await self._cleanup(job_id)
            elif info.state == JobState.FAILED:
                logger.warning(
                    "job %s failed: %s", job_id, info.error or "unknown error"
                )
                text = (
                    INFO_FAILED
                    if info.job_type == INFOGRAPHICS_JOB_TYPE
                    else JOB_FAILED
                )
                await self._deliver_terminal(info, text)
                await self._cleanup(job_id)
            elif info.state == JobState.CANCELLED:
                await self._deliver_terminal(info, JOB_CANCELLED)
                await self._cleanup(job_id)

    async def _update_progress(self, info: JobInfo) -> None:
        if not info.progress:
            return
        text = PROGRESS_STEPS.get(info.progress, ANALYSIS_LOADING)
        if self._progress_seen.get(info.id) == text:
            return
        message_id = _status_message_id(info)
        chat_id = _chat_id(info)
        if message_id is None or chat_id is None:
            return
        try:
            await self._sink.deliver(chat_id, text, edit_message_id=message_id)
        except Exception:  # noqa: BLE001
            logger.warning("job %s progress delivery failed", info.id)
            return
        self._progress_seen[info.id] = text

    async def _deliver_result(self, info: JobInfo) -> None:
        if not info.result:
            await self._deliver_terminal(info, JOB_FAILED)
            return
        if info.job_type == NICHE_SCAN_JOB_TYPE:
            report = NicheReport.model_validate_json(info.result)
            chat_id = _chat_id(info)
            if chat_id is None:
                logger.warning("job %s has no valid chat_id in payload", info.id)
                return
            await deliver_niche_report(
                self._sink,
                chat_id,
                report,
                status_message_id=_status_message_id(info),
                reply_markup=back_menu(),
            )
            return
        if info.job_type == SEO_JOB_TYPE:
            seo = SeoText.model_validate_json(info.result)
            chat_id = _chat_id(info)
            if chat_id is not None:
                # keep the report (and seller photos) for #62
                photos = await self._stash_photos(info, chat_id)
                await stash_seo(chat_id, seo.model_dump(mode="json"), photos)
            await self._deliver_terminal(
                info, render_seo_report(seo), reply_markup=seo_result_keyboard(seo)
            )
            return
        if info.job_type == INFOGRAPHICS_JOB_TYPE:
            artwork = RenderedArtwork.model_validate_json(info.result)
            await self._deliver_artwork(info, artwork)
            return
        if info.job_type == REVIEWS_JOB_TYPE:
            reviews_report = ReviewReport.model_validate_json(info.result)
            await self._deliver_terminal(
                info,
                render_reviews_report(reviews_report),
                reply_markup=reviews_result_keyboard(reviews_report),
            )
            return
        analysis = AnalysisReport.model_validate_json(info.result)
        await self._deliver_terminal(info, render_analysis_report(analysis))

    async def _deliver_artwork(self, info: JobInfo, artwork: RenderedArtwork) -> None:
        """Send rendered artwork as a photo, replacing the status message (#62)."""
        chat_id = _chat_id(info)
        if chat_id is None:
            logger.warning("job %s has no valid chat_id in payload", info.id)
            return
        await self._sink.deliver_photo(
            chat_id,
            render_infographic_caption(artwork.variant),
            base64.b64decode(artwork.image_b64),
            filename="infographic.png",
            reply_markup=infographic_variants(),
            edit_message_id=_status_message_id(info),
        )

    async def _deliver_terminal(
        self,
        info: JobInfo,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        chat_id = _chat_id(info)
        if chat_id is None:
            logger.warning("job %s has no valid chat_id in payload", info.id)
            return
        await self._sink.deliver(
            chat_id,
            text,
            reply_markup=reply_markup or back_menu(),
            edit_message_id=_status_message_id(info),
        )

    async def _stash_photos(self, info: JobInfo, chat_id: int) -> list[bytes] | None:
        """Download seller file_ids from the SEO payload; None best-effort."""
        if self._bot is None or info.payload is None:
            return None
        raw = info.payload.get("photo_file_ids")
        file_ids = (
            [f for f in raw if isinstance(f, str)] if isinstance(raw, list) else []
        )
        if not file_ids:
            return None
        try:
            photos = await download_photos(self._bot, file_ids)
        except Exception:  # noqa: BLE001 — stash still stores the report
            logger.warning("job %s: seller photo download failed", info.id)
            return None
        return photos or None

    async def _cleanup(self, job_id: str) -> None:
        redis = get_redis()
        await redis.srem(active_jobs_key(), job_id)
        await redis.delete(job_key(job_id))
        self._progress_seen.pop(job_id, None)


def _chat_id(info: JobInfo) -> int | None:
    if info.payload is None:
        return None
    try:
        return int(info.payload["chat_id"])
    except KeyError, TypeError, ValueError:
        return None


def _status_message_id(info: JobInfo) -> int | None:
    if info.payload is None:
        return None
    raw = info.payload.get("status_message_id")
    try:
        return int(raw)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None


async def start_job_poller(bot: Bot) -> JobPoller:
    poller = JobPoller(get_job_runner(), AiogramResultSink(bot), bot=bot)
    poller.start()
    return poller
