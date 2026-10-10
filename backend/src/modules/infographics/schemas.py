"""Infographic contracts: style variants and text plates (issue #62).

Three style variants, each composed of deterministic text plates derived
from the SEO output (title, bullets, keywords); the plates are rendered
into an image by the LLM image provider (TODO(F15): prompt registry).
"""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.modules.content.schemas import SeoText

MAX_PLATES = 6  # widest variant budget (Bright/Sale)

IMAGE_SIZE = "1024x1024"  # square 1:1 poster


class StyleVariant(StrEnum):
    """Frozen set of infographic style variants (issue #62)."""

    MINIMALISM = "minimalism"
    PREMIUM = "premium"
    BRIGHT_SALE = "bright_sale"


class PlateKind(StrEnum):
    """Role of one text block inside a plate set."""

    HEADER = "header"
    FEATURE = "feature"
    KEYWORDS = "keywords"


@dataclass(frozen=True)
class PlateLimits:
    """Per-variant plate budget (mirrors content.SeoLimits)."""

    plates: int  # total plates including the header
    features: int  # feature plates cut from bullets
    plate_len: int  # max characters per plate


PLATE_LIMITS: dict[StyleVariant, PlateLimits] = {
    StyleVariant.MINIMALISM: PlateLimits(plates=4, features=3, plate_len=60),
    StyleVariant.PREMIUM: PlateLimits(plates=5, features=4, plate_len=70),
    StyleVariant.BRIGHT_SALE: PlateLimits(plates=6, features=5, plate_len=80),
}


class Plate(BaseModel):
    """One text block to be rendered onto the image."""

    kind: PlateKind
    text: str = Field(min_length=1, max_length=80)


class PlateSet(BaseModel):
    """Plates for one variant in layout order: header, features, keywords."""

    variant: StyleVariant
    plates: list[Plate] = Field(min_length=1, max_length=MAX_PLATES)


class InfographicRequest(BaseModel):
    """Build request: SEO output plus the chosen style variant."""

    model_config = ConfigDict(extra="ignore")  # chat_id/status_message_id ride along

    seo: SeoText
    variant: StyleVariant


class RenderedArtwork(BaseModel):
    """Job result: one generated image as JSON-safe payload (issue #62)."""

    model_config = ConfigDict(extra="ignore")

    variant: StyleVariant
    mime: str = "image/png"
    image_b64: str = Field(min_length=1)
