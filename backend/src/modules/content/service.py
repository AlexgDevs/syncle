"""SEO text generation service (issues #22, #24, #25).

Flow: build prompt -> LLM call -> JSON parse -> pydantic validation ->
marketplace clamp; one repair retry with the validation errors, then
`SeoGenerationError`. LLM timeout/rate-limit errors surface as-is (they
are domain exceptions by contract, ADR-002).
"""

import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache

from pydantic import ValidationError

from src.core.llm import LLMProvider, get_llm_provider
from src.core.llm.json_output import extract_json_object
from src.modules.content.errors import SeoGenerationError
from src.modules.content.prompts import (
    SEO_MAX_TOKENS,
    SEO_SYSTEM,
    SEO_TEMPERATURE,
    build_seo_prompt,
    build_seo_repair_prompt,
)
from src.modules.content.schemas import SEO_LIMITS, SeoLimits, SeoRequest, SeoText

logger = logging.getLogger(__name__)

SEO_PROGRESS_STEP = "generating_seo"
_REPAIR_ATTEMPTS = 1


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    return text[:limit].rstrip() if len(text) > limit else text


def _clamp(text: SeoText, limits: SeoLimits) -> SeoText:
    """Enforce marketplace field limits (#25); never rejects, only trims."""
    bullets = [
        item for item in (_cut(b, limits.bullet_len) for b in text.bullets) if item
    ]
    keywords = [
        item for item in (_cut(k, limits.keyword_len) for k in text.keywords) if item
    ]
    return SeoText(
        title=_cut(text.title, limits.title),
        description=_cut(text.description, limits.description),
        bullets=bullets[: limits.bullets],
        keywords=keywords[: limits.keywords],
    )


def _validation_errors(exc: ValidationError) -> list[str]:
    errors = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "root"
        errors.append(f"{loc}: {error['msg']}")
    return errors or ["invalid output"]


class SeoService:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    async def generate(
        self,
        request: SeoRequest,
        *,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> SeoText:
        """Generate a validated SEO block for one request (#24)."""
        llm = self.llm
        if llm is None:
            raise SeoGenerationError("LLM is not configured")
        if on_progress is not None:
            await on_progress(SEO_PROGRESS_STEP)

        prompt = build_seo_prompt(request)
        raw = await llm.complete(
            prompt,
            system=SEO_SYSTEM,
            temperature=SEO_TEMPERATURE,
            max_tokens=SEO_MAX_TOKENS,
        )
        text, errors = self._parse_output(raw, request)
        for _ in range(_REPAIR_ATTEMPTS):
            if text is not None:
                break
            logger.warning("SEO output invalid, repairing: %s", "; ".join(errors[:3]))
            raw = await llm.complete(
                build_seo_repair_prompt(request, errors),
                system=SEO_SYSTEM,
                temperature=SEO_TEMPERATURE,
                max_tokens=SEO_MAX_TOKENS,
            )
            text, errors = self._parse_output(raw, request)
        if text is None:
            raise SeoGenerationError(
                "SEO output failed validation: " + "; ".join(errors[:3])
            )
        return text

    def _parse_output(
        self, raw: str, request: SeoRequest
    ) -> tuple[SeoText | None, list[str]]:
        """Parse and validate one completion; returns (text, errors)."""
        data = extract_json_object(raw)
        if data is None:
            return None, ["response is not a JSON object"]
        try:
            text = SeoText.model_validate(data)
        except ValidationError as exc:
            return None, _validation_errors(exc)
        return _clamp(text, SEO_LIMITS[request.marketplace]), []


@lru_cache
def get_seo_service() -> SeoService:
    """Process-wide singleton: shares the LLM provider (#24)."""
    return SeoService(llm=get_llm_provider())
