"""Plate builder and image generation pipeline (issue #62, v4/v5).

Plates turn a SeoText into per-style text blocks without an LLM call:
title -> header, bullets -> feature plates, keywords -> strip. The
description stays out of the poster; it belongs to the marketplace page.

render() runs two steps (M7-v5): a text LLM structures the customer's
brief into BriefOverrides (BRIEF_SYSTEM; failures degrade to the raw
brief as the product information), then build_gemini_prompt() fills the
art-director brief (assets/prompts/poster-gemini.txt) and the Gemini
image model on AITunnel paints the finished poster — product photo,
Russian text and style all in one shot, no local composition layer.
"""

import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache

from src.core.llm import LLMError, get_image_provider, get_llm_provider
from src.core.llm.provider import ImageProvider, LLMProvider
from src.modules.infographics.errors import InfographicsError, InfographicsRenderError
from src.modules.infographics.prompts import (
    BRIEF_SYSTEM,
    BriefOverrides,
    build_brief_user,
    build_gemini_prompt,
    parse_brief,
)
from src.modules.infographics.schemas import (
    IMAGE_SIZE,
    PLATE_LIMITS,
    InfographicRequest,
    Plate,
    PlateKind,
    PlateSet,
)

logger = logging.getLogger(__name__)


def _clamp(text: str, limit: int) -> str:
    """Collapse whitespace and clip to the plate budget."""
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1].rstrip() + "…"


class InfographicsService:
    """Builds style-specific plates from a SeoText and renders them (#62)."""

    def __init__(
        self,
        image: ImageProvider | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self._image = image
        self._llm = llm

    def build_plates(self, request: InfographicRequest) -> PlateSet:
        seo = request.seo
        limits = PLATE_LIMITS[request.variant]
        header = _clamp(seo.title, limits.plate_len)
        if not header:
            raise InfographicsError("seo title is blank")
        plates = [Plate(kind=PlateKind.HEADER, text=header)]
        features = 0
        for bullet in seo.bullets:
            if features >= limits.features or len(plates) >= limits.plates:
                break
            text = _clamp(bullet, limits.plate_len) if bullet.strip() else ""
            if text:
                plates.append(Plate(kind=PlateKind.FEATURE, text=text))
                features += 1
        if seo.keywords and len(plates) < limits.plates:
            strip = " · ".join(
                word for word in (keyword.strip() for keyword in seo.keywords) if word
            )
            text = _clamp(strip, limits.plate_len)
            if text:
                plates.append(Plate(kind=PlateKind.KEYWORDS, text=text))
        return PlateSet(variant=request.variant, plates=plates)

    async def _structure_brief(
        self, request: InfographicRequest, plates: PlateSet, brief: str
    ) -> BriefOverrides | None:
        """Brief structuring LLM -> overrides; None falls back to raw text."""
        if self._llm is None:
            logger.warning("brief structuring skipped: no LLM provider")
            return None
        try:
            raw = await self._llm.complete(
                build_brief_user(request, plates, brief),
                system=BRIEF_SYSTEM,
                temperature=0.3,
            )
        except LLMError as exc:
            logger.warning("brief structuring degraded: %s", exc)
            return None
        try:
            return parse_brief(raw)
        except Exception as exc:  # noqa: BLE001 — JSON/pydantic validation
            logger.warning("brief structuring returned bad JSON: %s", exc)
            return None

    async def render(
        self,
        request: InfographicRequest,
        *,
        photos: list[bytes] | None = None,
        brief: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> bytes:
        """Generate the poster image for `request` (issue #62, v4/v5).

        ``photos`` are seller product shots attached as image input of the
        edits call; without them the model composes the product from the
        text description. ``brief`` is the customer's own description of
        the poster (M7-v5): a text LLM structures it into template
        overrides; when that layer fails the raw brief becomes the
        product information, so customer specifics are never dropped.

        Raises:
            InfographicsRenderError: image provider missing or failed.
        """
        if self._image is None:
            raise InfographicsRenderError(
                "image generation is not configured (set AITUNNEL_API_KEY)"
            )
        plates = self.build_plates(request)
        overrides: BriefOverrides | None = None
        structured = False
        if brief:
            if on_progress is not None:
                await on_progress("structuring_brief")
            overrides = await self._structure_brief(request, plates, brief)
            if overrides is None:  # degraded: raw customer brief, no LLM layer
                overrides = BriefOverrides(product_information=brief.strip()[:1500])
            else:
                structured = True
        if on_progress is not None:
            await on_progress("composing_prompt")
        prompt = build_gemini_prompt(
            request, plates, has_photo=bool(photos), overrides=overrides
        )
        if on_progress is not None:
            await on_progress("rendering_image")
        try:
            data = await self._image.generate_image(
                prompt, size=IMAGE_SIZE, images=photos or None
            )
        except LLMError as exc:
            raise InfographicsRenderError(f"image generation failed: {exc}") from exc
        if not data:
            raise InfographicsRenderError("image provider returned empty data")
        logger.info(
            "infographic rendered: variant=%s plates=%d photos=%d bytes=%d "
            "prompt=%d brief=%s",
            request.variant,
            len(plates.plates),
            len(photos or []),
            len(data),
            len(prompt),
            "structured" if structured else ("raw" if brief else "-"),
        )
        return data


@lru_cache
def get_infographics_service() -> InfographicsService:
    """Process-wide singleton (convention of the sibling modules)."""
    return InfographicsService(
        image=get_image_provider(),
        llm=get_llm_provider(),
    )
