"""SEO text schemas (issue #22).

The input contract is deliberately narrow: a free-text product
description plus optional attributes (from vision, #27) and optional
advantages; the output is a validated, marketplace-clamped SEO block.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from src.modules.analytics.enums import Marketplace

MAX_ADVANTAGES = 3
MAX_KEY_FEATURES = 3


@dataclass(frozen=True)
class SeoLimits:
    """Field length limits of one marketplace (#23)."""

    title: int
    description: int
    bullets: int
    bullet_len: int
    keywords: int
    keyword_len: int


SEO_LIMITS: dict[Marketplace, SeoLimits] = {
    Marketplace.WB: SeoLimits(
        title=60,
        description=1000,
        bullets=5,
        bullet_len=150,
        keywords=10,
        keyword_len=50,
    ),
    Marketplace.OZON: SeoLimits(
        title=100,
        description=1500,
        bullets=5,
        bullet_len=150,
        keywords=10,
        keyword_len=50,
    ),
}


class SeoAttributes(BaseModel):
    """Product attributes extracted from photos by the vision model (#27)."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    category: str | None = None
    brand: str | None = None
    key_features: list[str] = Field(default_factory=list)


class SeoRequest(BaseModel):
    """Input contract for SEO generation (issue #22).

    Extra keys are ignored so the bot can submit the request together
    with delivery metadata (chat_id, status_message_id) as one payload.
    """

    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1)
    marketplace: Marketplace
    advantages: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    key_features: list[str] = Field(default_factory=list)


class SeoText(BaseModel):
    """Generated SEO block (issue #22); clamped to SeoLimits after parse."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
