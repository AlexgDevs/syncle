"""Review analysis schemas (issues #28, #32).

Input contract: a tone plus one or two resolved sources (own and/or
rival) — the bot fetches SKU reviews and resolves the selection before
submitting. Output: findings grouped by unique RU tags in the
``#Проблема_Упаковка`` format.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.analytics.schemas import Review

MAX_SOURCES = 2
MAX_FINDINGS = 8
MAX_POINTS_PER_TAG = 3
# 3 points x 80 chars + separators keep a group's copy payload <= 256
# (Telegram CopyTextButton limit, see bot keyboards).
MAX_POINT_LEN = 80


class Tone(StrEnum):
    NEUTRAL = "neutral"
    SOFT = "soft"
    HARSH = "harsh"


class ReviewSource(BaseModel):
    """Resolved texts of one product (own or rival, issue #32)."""

    model_config = ConfigDict(extra="ignore")

    role: Literal["own", "rival"]
    description: str | None = None
    reviews: list[Review] = Field(default_factory=list)


class ReviewAnalysisRequest(BaseModel):
    """Input contract for review analysis (issue #28).

    Extra keys are ignored so the bot can submit delivery metadata
    (chat_id, status_message_id) in the same payload.
    """

    model_config = ConfigDict(extra="ignore")

    tone: Tone
    sources: list[ReviewSource] = Field(min_length=1, max_length=MAX_SOURCES)


class Finding(BaseModel):
    """One problem group: RU tag plus short evidence points (issue #28)."""

    model_config = ConfigDict(extra="ignore")

    tag: str = Field(min_length=2)
    points: list[str] = Field(min_length=1)


class FindingsOutput(BaseModel):
    """Raw LLM output shape: a non-empty findings list (#30)."""

    model_config = ConfigDict(extra="ignore")

    findings: list[Finding] = Field(min_length=1)


class ReviewReport(BaseModel):
    """Generated findings grouped by unique tags (issue #28)."""

    model_config = ConfigDict(extra="ignore")

    tone: Tone
    findings: list[Finding] = Field(min_length=1)
