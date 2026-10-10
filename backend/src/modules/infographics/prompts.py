"""Gemini poster prompt (issue #62, pipeline v4/v5).

The art-director brief lives in ``backend/assets/prompts/poster-gemini.txt``
(~21k chars, under AITunnel's 32k edits limit); this module only fills its
placeholders from the SEO output and the chosen style variant. Product
photos travel as image input of the edits call — the brief only tells the
model that a photo is attached.

M7-v5: the customer's own brief (what to show, exact wording) is first
structured by a text LLM into ``BriefOverrides`` (BRIEF_SYSTEM) — English
for descriptive fields, verbatim Russian for anything rendered on the
poster — and non-empty overrides win over the SEO-derived defaults.

TODO(F15): move to a versioned prompt registry shared by all modules.
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.modules.infographics.schemas import (
    InfographicRequest,
    PlateKind,
    PlateSet,
    StyleVariant,
)

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE_NAME = "poster-gemini.txt"

PROMPT_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "assets" / "prompts"

PHOTO_PRESENT = (
    "Attached as image input — this photo is the visual reference: keep "
    "the product's shape, colors and details exactly."
)
PHOTO_MISSING = (
    "No photo attached — compose the product from the text description "
    "only, without inventing brand marks."
)

TARGET_AUDIENCE_DEFAULT = (
    "Russian marketplace shoppers (Wildberries/Ozon) scrolling the "
    "product card and comparing offers"
)

BRAND_STYLES: dict[StyleVariant, str] = {
    StyleVariant.MINIMALISM: (
        "minimalism — clean white background, generous whitespace, thin "
        "sans-serif typography, one restrained accent color, flat shapes"
    ),
    StyleVariant.PREMIUM: (
        "premium — deep dark palette (charcoal or navy), gold or champagne "
        "serif accents, elegant thin lines, luxury editorial feel"
    ),
    StyleVariant.BRIGHT_SALE: (
        "bright sale — saturated warm gradients, bold heavy typography, "
        "price-tag shapes and starburst badges, energetic playful accents"
    ),
}


class BriefOverrides(BaseModel):
    """Customer-driven values for the template placeholders (M7-v5).

    Empty fields mean "keep the SEO-derived default"; text fields carry
    the customer's exact wording (Russian) where they provided one.
    """

    model_config = ConfigDict(extra="ignore")

    product_name: str = Field(default="", max_length=200)
    product_information: str = Field(default="", max_length=1500)
    key_features: list[str] = Field(default_factory=list, max_length=5)
    optional_text: str = Field(default="", max_length=200)
    brand_style: str = Field(default="", max_length=500)
    target_audience: str = Field(default="", max_length=300)


BRIEF_SYSTEM = """\
You turn a customer's brief (Russian) into ONE structured JSON input for \
an AI art director that renders marketplace product posters.

Input you receive: the customer's brief (what they want to see on the \
poster and which exact words to use), the SEO copy (product facts), and \
the text plates (lines that must fit the poster).

Output ONLY one JSON object — no markdown fences, no commentary:
{
  "product_name": "short poster title",
  "product_information": "product description for the poster",
  "key_features": ["feature line", "..."],
  "optional_text": "extra small text row",
  "brand_style": "style and art direction",
  "target_audience": "who the poster targets"
}

Rules:
- product_name, key_features, optional_text: RUSSIAN and VERBATIM from \
the customer's brief whenever the customer supplied wording — never \
translate, reword, shorten or invent these lines; they are rendered on \
the image character for character. Keep them within the plate budget: \
product_name <= 60 chars, up to 5 key_features each <= 80 chars, \
optional_text <= 80 chars.
- product_information, brand_style, target_audience: ENGLISH. Merge the \
customer's wishes (layout, props, colors, mood, must-show elements) with \
the SEO facts — concrete beats generic; honor every explicit request.
- key_features: the customer's feature lines first; add SEO bullets only \
when the brief has no features.
- optional_text: the customer's extra wording, else the SEO keywords.
- No new claims, no prices, no guarantees the customer did not mention.
"""


def build_brief_user(
    request: InfographicRequest, plate_set: PlateSet, brief: str
) -> str:
    """User message for brief structuring: customer brief + SEO facts."""
    seo = request.seo
    lines = [
        f"Style variant: {request.variant.value}",
        "",
        "Customer brief (RU):",
        brief.strip(),
        "",
        "SEO facts:",
        f"Product name: {seo.title}",
        f"Description: {seo.description}",
    ]
    if seo.bullets:
        lines.append("Bullets: " + " | ".join(seo.bullets))
    if seo.keywords:
        lines.append("Keywords: " + ", ".join(seo.keywords))
    lines.append("")
    lines.append("Text plates (poster lines, clipped to budget):")
    for plate in plate_set.plates:
        lines.append(f"- {plate.kind.value}: {plate.text}")
    return "\n".join(lines)


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_brief(raw: str) -> BriefOverrides:
    """Parse the structuring LLM's JSON reply into BriefOverrides.

    Raises (pydantic) ValidationError / json.JSONDecodeError on garbage —
    callers fall back to the raw customer brief.
    """
    text = raw.strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("brief structuring reply contains no JSON object")
    data: Any = json.loads(text[start : end + 1])
    return BriefOverrides.model_validate(data)


@lru_cache
def load_prompt_template() -> str:
    """Raw art-director brief from backend/assets/prompts (once per process)."""
    return (PROMPT_TEMPLATE_DIR / PROMPT_TEMPLATE_NAME).read_text(encoding="utf-8")


def build_gemini_prompt(
    request: InfographicRequest,
    plate_set: PlateSet,
    *,
    has_photo: bool,
    overrides: BriefOverrides | None = None,
) -> str:
    """Fill the brief's placeholders from the SEO copy and the style.

    Header/features/keywords come from the plate set (already clipped to
    the variant budget), so the model receives exactly the lines that fit
    the poster. Non-empty ``overrides`` (the customer's structured brief)
    win over those defaults. Unknown placeholders are impossible: the
    template's seven keys are all replaced here.
    """
    seo = request.seo
    header = next(
        (plate.text for plate in plate_set.plates if plate.kind == PlateKind.HEADER),
        seo.title,
    )
    features = [
        plate.text for plate in plate_set.plates if plate.kind == PlateKind.FEATURE
    ]
    keywords = next(
        (plate.text for plate in plate_set.plates if plate.kind == PlateKind.KEYWORDS),
        "",
    )
    replacements = {
        "{PRODUCT_IMAGE}": PHOTO_PRESENT if has_photo else PHOTO_MISSING,
        "{PRODUCT_NAME}": header,
        "{PRODUCT_INFORMATION}": seo.description or "not provided",
        "{KEY_FEATURES}": "\n".join(f"- {item}" for item in features) or "not provided",
        "{TARGET_AUDIENCE}": TARGET_AUDIENCE_DEFAULT,
        "{BRAND_STYLE}": BRAND_STYLES[request.variant],
        "{OPTIONAL_TEXT}": keywords or "none",
    }
    if overrides is not None:
        if overrides.product_name.strip():
            replacements["{PRODUCT_NAME}"] = overrides.product_name.strip()
        if overrides.product_information.strip():
            replacements["{PRODUCT_INFORMATION}"] = (
                overrides.product_information.strip()
            )
        stripped = [item.strip() for item in overrides.key_features if item.strip()]
        if stripped:
            replacements["{KEY_FEATURES}"] = "\n".join(f"- {item}" for item in stripped)
        if overrides.optional_text.strip():
            replacements["{OPTIONAL_TEXT}"] = overrides.optional_text.strip()
        if overrides.brand_style.strip():
            replacements["{BRAND_STYLE}"] = overrides.brand_style.strip()
        if overrides.target_audience.strip():
            replacements["{TARGET_AUDIENCE}"] = overrides.target_audience.strip()
    text = load_prompt_template()
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text
