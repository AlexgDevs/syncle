"""Background job handlers for the infographics module (issue #62).

Handlers receive the payload and a `JobContext`, and return the
serialized result (JSON). Step codes passed to `ctx.progress` are
mapped to RU text by the bot (`src.bot.texts.PROGRESS_STEPS`).

Payload stays light — chat_id, variant, status_message_id — the SEO
report and product photos are read from the Redis stash (see
src.core.stash) by chat_id. The customer brief (M7-v5) and any fresh
photos live under their own stash key written by the scene handler;
without it the poster renders from the SEO copy alone (legacy path).
"""

import base64
from typing import Any

from src.core.jobs.base import JobContext, JobHandler
from src.core.jobs.registry import register_job_handlers
from src.core.stash import load_brief, load_stashed_entry
from src.modules.content import SeoText
from src.modules.infographics import (
    InfographicRequest,
    InfographicsRenderError,
    RenderedArtwork,
    StyleVariant,
    get_infographics_service,
)

INFOGRAPHICS_JOB_TYPE = "infographics_render"

INFOGRAPHICS_RETRIES: dict[str, int] = {
    INFOGRAPHICS_JOB_TYPE: 1,
}


async def infographics_render_job(payload: dict[str, Any], context: JobContext) -> str:
    """Render one poster image (issue #62).

    Raises InfographicsRenderError when the stashed SEO entry expired —
    the bot then answers with a regeneration hint.
    """
    try:
        chat_id = int(payload["chat_id"])
        variant = StyleVariant(payload["variant"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InfographicsRenderError(
            "infographics payload misses chat_id/variant"
        ) from exc
    entry = await load_stashed_entry(chat_id)
    if entry is None:
        raise InfographicsRenderError("stashed SEO expired for this chat")
    brief_entry = await load_brief(chat_id)
    request = InfographicRequest(seo=SeoText.model_validate(entry.seo), variant=variant)
    # fresh customer photos win over the SEO-era stash; brief is optional
    # (legacy renders from SEO alone)
    photos = (
        brief_entry.photos
        if brief_entry is not None and brief_entry.photos
        else entry.photos
    )
    data = await get_infographics_service().render(
        request,
        photos=photos or None,
        brief=brief_entry.brief if brief_entry is not None else None,
        on_progress=context.progress,
    )
    artwork = RenderedArtwork(
        variant=request.variant,
        image_b64=base64.b64encode(data).decode("ascii"),
    )
    return artwork.model_dump_json()


INFOGRAPHICS_HANDLERS: dict[str, JobHandler] = {
    INFOGRAPHICS_JOB_TYPE: infographics_render_job,
}


def register_infographics_jobs() -> None:
    """Register infographics handlers (called by the worker root)."""
    register_job_handlers(INFOGRAPHICS_HANDLERS, INFOGRAPHICS_RETRIES)
