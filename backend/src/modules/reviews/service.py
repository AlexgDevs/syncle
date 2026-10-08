"""Review analysis service (issues #28, #29, #30).

Flow: build prompt -> LLM call -> JSON parse -> pydantic validation
(includes the tag format check) -> tag dedup + clamp; one repair retry
carries the validation errors, then `ReviewAnalysisError`. LLM
timeout/rate-limit errors surface as-is (ADR-002).
"""

import logging
import re
from collections.abc import Awaitable, Callable
from functools import lru_cache

from pydantic import ValidationError

from src.core.llm import LLMProvider, get_llm_provider
from src.core.llm.json_output import extract_json_object
from src.modules.reviews.errors import ReviewAnalysisError
from src.modules.reviews.prompts import (
    REVIEWS_MAX_TOKENS,
    REVIEWS_SYSTEM,
    REVIEWS_TEMPERATURE,
    build_reviews_prompt,
    build_reviews_repair_prompt,
)
from src.modules.reviews.schemas import (
    MAX_FINDINGS,
    MAX_POINT_LEN,
    MAX_POINTS_PER_TAG,
    FindingsOutput,
    Finding,
    ReviewAnalysisRequest,
    ReviewReport,
)

logger = logging.getLogger(__name__)

ANALYSIS_PROGRESS_STEP = "analyzing_reviews"
_REPAIR_ATTEMPTS = 1

# Tag contract (#29): #Проблема_Упаковка — one token, underscore-separated
# words, no spaces. Cyrillic/Latin letters and digits only.
TAG_PATTERN = re.compile(r"^#[0-9A-Za-zА-Яа-яЁё]+(_[0-9A-Za-zА-Яа-яЁё]+)*$")


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    return text[:limit].rstrip() if len(text) > limit else text


def _validation_errors(exc: ValidationError) -> list[str]:
    errors = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "root"
        errors.append(f"{loc}: {error['msg']}")
    return errors or ["invalid output"]


def _tag_format_errors(findings: list[Finding]) -> list[str]:
    errors = []
    for index, finding in enumerate(findings):
        if not TAG_PATTERN.match(finding.tag.strip()):
            errors.append(f"findings[{index}].tag: invalid tag format: {finding.tag!r}")
    return errors


def _normalize(findings: list[Finding]) -> list[Finding]:
    """Dedup tags case-insensitively, merge points, clamp budgets (#30)."""
    points_by_tag: dict[str, list[str]] = {}
    tag_order: list[str] = []
    for finding in findings:
        tag = finding.tag.strip()
        key = tag.casefold()
        if key not in points_by_tag:
            points_by_tag[key] = []
            tag_order.append(tag)
        bucket = points_by_tag[key]
        for raw_point in finding.points:
            point = _cut(raw_point, MAX_POINT_LEN)
            if point and point not in bucket:
                bucket.append(point)
    normalized: list[Finding] = []
    for tag in tag_order[:MAX_FINDINGS]:
        points = points_by_tag[tag.casefold()][:MAX_POINTS_PER_TAG]
        if points:
            normalized.append(Finding(tag=tag, points=points))
    return normalized


class ReviewAnalysisService:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self.llm = llm

    async def analyze(
        self,
        request: ReviewAnalysisRequest,
        *,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> ReviewReport:
        """Generate validated findings for one request (#30)."""
        llm = self.llm
        if llm is None:
            raise ReviewAnalysisError("LLM is not configured")
        if on_progress is not None:
            await on_progress(ANALYSIS_PROGRESS_STEP)

        prompt = build_reviews_prompt(request)
        raw = await llm.complete(
            prompt,
            system=REVIEWS_SYSTEM,
            temperature=REVIEWS_TEMPERATURE,
            max_tokens=REVIEWS_MAX_TOKENS,
        )
        findings, errors = self._parse_output(raw)
        for _ in range(_REPAIR_ATTEMPTS):
            if findings is not None:
                break
            logger.warning(
                "reviews output invalid, repairing: %s", "; ".join(errors[:3])
            )
            raw = await llm.complete(
                build_reviews_repair_prompt(request, errors),
                system=REVIEWS_SYSTEM,
                temperature=REVIEWS_TEMPERATURE,
                max_tokens=REVIEWS_MAX_TOKENS,
            )
            findings, errors = self._parse_output(raw)
        if findings is None:
            raise ReviewAnalysisError(
                "Review analysis failed validation: " + "; ".join(errors[:3])
            )
        normalized = _normalize(findings)
        if not normalized:
            raise ReviewAnalysisError("No valid findings after validation")
        return ReviewReport(tone=request.tone, findings=normalized)

    def _parse_output(self, raw: str) -> tuple[list[Finding] | None, list[str]]:
        """Parse one completion; returns (findings, errors) (#30)."""
        data = extract_json_object(raw)
        if data is None:
            return None, ["response is not a JSON object"]
        try:
            output = FindingsOutput.model_validate(data)
        except ValidationError as exc:
            return None, _validation_errors(exc)
        errors = _tag_format_errors(output.findings)
        if errors:
            return None, errors
        return output.findings, []


@lru_cache
def get_reviews_service() -> ReviewAnalysisService:
    """Process-wide singleton: shares the LLM provider (#30)."""
    return ReviewAnalysisService(llm=get_llm_provider())
