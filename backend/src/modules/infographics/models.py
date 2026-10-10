"""Manual-test registry of image models with pricing notes (issue #62).

Primary path (pipeline v4): AITunnel (aitunnel.ru, RUB prepay) serves the
Gemini image models below — set AITUNNEL_API_KEY in .env and they own
image generation. Prices come from the AITunnel catalog (Oct 2026); the
true cost per poster is reported by `usage` in the API response (run
smoke_m7_models.py to measure one image per model).

Fallback path: proxyapi.ru model catalog (RUB incl. VAT) via
LLM_IMAGE_MODEL — token-priced models show per-million-token rates.
Non-OpenAI vendors live on the unified API base `https://api.proxyapi.ru/v1`
and need the `vendor/` prefix; the legacy `/openai/v1` base serves only the
OpenAI family (gpt-image-1 stays short-name compatible there).

Optional quality knob (low/medium/high) via LLM_IMAGE_QUALITY — proxyapi
gpt-image family only.
"""

from dataclasses import dataclass

DEFAULT_IMAGE_MODEL = "gpt-image-1"
DEFAULT_IMAGE_QUALITY = "medium"  # ~12.80 ₽/1024² image


@dataclass(frozen=True)
class ImageModel:
    """One testable model with its pricing/compatibility notes."""

    id: str
    price: str  # RUB rates from the provider docs
    i2i: bool  # accepts input photos (images/edits)
    notes: str


IMAGE_MODELS: tuple[ImageModel, ...] = (
    ImageModel(
        id="gemini-3.1-flash-image",
        price="AI Tunnel, ~13 ₽/фото (замер 10.2026)",
        i2i=True,
        notes="основная v4; images/edits с фото, prompt до 32k",
    ),
    ImageModel(
        id="gemini-3.1-flash-lite-image",
        price="AI Tunnel, дешевле ~13 ₽/фото base (замер в процессе)",
        i2i=True,
        notes="текущая в .env; дешёвый вариант v4",
    ),
    ImageModel(
        id="gemini-2.5-flash-image",
        price="AI Tunnel: in 57.6 ₽/М, out 480 ₽/М ток.",
        i2i=True,
        notes="запасная image-модель AITunnel",
    ),
    ImageModel(
        id="tencent/hy-image-v3.5-preview",
        price="221.05 ₽/М ток. — самый дешёвый (~1 ₽/фото)",
        i2i=False,
        notes="Tencent Hy; т2и; сцену проверить визуально",
    ),
    ImageModel(
        id="recraft/recraft-v4.1-flash",
        price="231.58 ₽/М ток. (~1 ₽/фото)",
        i2i=False,
        notes="recraft: сильный дизайн; т2и; сцену проверить",
    ),
    ImageModel(
        id="gpt-image-1",
        price="3.30 / 12.80 / 50.45 ₽/фото (low/med/high); вх.фото 3040 ₽/М ток.",
        i2i=True,
        notes="кириллица идеально (проверено); дефолт, quality=medium",
    ),
    ImageModel(
        id="gpt-image-2.5-sunburst",
        price="out 9100 ₽/М ток.",
        i2i=True,
        notes="яркие градиенты; quality не принимает (bare retry)",
    ),
    ImageModel(
        id="gpt-image-2.5-flare",
        price="out 9100 ₽/М ток.",
        i2i=True,
        notes="контрастный свет; quality не принимает (bare retry)",
    ),
    ImageModel(
        id="bytedance-seed/seedream-5-0-flash",
        price="578.95 ₽/М ток. — самый дешёвый",
        i2i=True,
        notes="кириллицу проверить; unified /v1 base",
    ),
    ImageModel(
        id="black-forest-labs/flux-3-image",
        price="663.16 ₽/М ток.",
        i2i=True,
        notes="слаб с русским текстом — риск кракозябр (в гибриде неважно)",
    ),
    ImageModel(
        id="qwen/qwen-image-3",
        price="968.42 ₽/М ток.",
        i2i=True,
        notes="хорош с кириллицей по слухам; проверить",
    ),
    ImageModel(
        id="recraft/recraft-v4-styles",
        price="1157.89 ₽/М ток.",
        i2i=False,
        notes="только t2i; сильные стили",
    ),
)

IMAGE_MODELS_BY_ID: dict[str, ImageModel] = {m.id: m for m in IMAGE_MODELS}


def model_note(model_id: str) -> str:
    """Pricing/compat comment for `model_id`, or a short unknown marker."""
    model = IMAGE_MODELS_BY_ID.get(model_id)
    if model is None:
        return f"{model_id} — цена неизвестна (нет в реестре)"
    i2i = "i2i✓" if model.i2i else "t2i только"
    return f"{model.id} — {model.price}; {i2i}; {model.notes}"
