"""Short-lived Redis stash for the last generated SeoText (issue #62).

The infographic entry point lives on the SEO result keyboard, but both
delivery paths (inline FSM and taskiq) clear state before it is pressed;
the last report is kept per chat so the poster can be rendered later.

Payload (JSON): ``{"seo": {...}, "photos": ["<b64>", ...]}`` — photos are
seller product shots (base64) fed to the images/edits endpoint. Entries
written by older builds stored the bare SEO dict; readers accept both
shapes.

The per-poster customer brief (M7-v5) lives under its own key
(``syncle:stash:infobrief:{chat_id}``) so writing it never disturbs the
SEO report: ``{"brief": "...", "photos": ["<b64>", ...]}``.
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.core.redis import get_redis

logger = logging.getLogger(__name__)

STASH_TTL_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class StashEntry:
    """Stashed SEO report plus its product photos (bytes)."""

    seo: dict[str, Any]
    photos: list[bytes] = field(default_factory=list)


@dataclass(frozen=True)
class BriefEntry:
    """Stashed customer brief (M7-v5) plus freshly sent photos (bytes)."""

    brief: str
    photos: list[bytes] = field(default_factory=list)


def _stash_key(chat_id: int) -> str:
    return f"syncle:stash:seo:{chat_id}"


def _brief_key(chat_id: int) -> str:
    return f"syncle:stash:infobrief:{chat_id}"


def _encode_photos(photos: list[bytes] | None) -> list[str]:
    return [base64.b64encode(photo).decode("ascii") for photo in photos or []]


def _decode_photos(raw: Any) -> list[bytes]:
    photos: list[bytes] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                try:
                    photos.append(base64.b64decode(item))
                except ValueError:
                    logger.warning("stash photo unreadable; skipping")
    return photos


async def stash_seo(
    chat_id: int,
    text: dict[str, Any],
    photos: list[bytes] | None = None,
) -> None:
    """Remember the report (and photos) for the chat; failures only drop
    the shortcut."""
    payload: dict[str, Any] = {"seo": text, "photos": _encode_photos(photos)}
    try:
        await get_redis().set(
            _stash_key(chat_id),
            json.dumps(payload, ensure_ascii=False),
            ex=STASH_TTL_SECONDS,
        )
    except Exception:  # noqa: BLE001 — entry point degrades to a hint
        logger.warning("seo stash write failed", exc_info=True)


async def load_stashed_entry(chat_id: int) -> StashEntry | None:
    """Return the stored report and photos, or None on absence/expiry."""
    try:
        raw = await get_redis().get(_stash_key(chat_id))
    except Exception:  # noqa: BLE001 — the scene answers with a hint
        logger.warning("seo stash read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("seo"), dict):  # pre-v2 bare SeoText shape
        return StashEntry(seo=data)
    return StashEntry(seo=data["seo"], photos=_decode_photos(data.get("photos")))


async def stash_brief(
    chat_id: int, brief: str, photos: list[bytes] | None = None
) -> None:
    """Remember the customer brief (M7-v5) plus fresh photos for the chat.

    Failures only drop the brief: the poster then renders from SEO alone.
    """
    payload: dict[str, Any] = {"brief": brief, "photos": _encode_photos(photos)}
    try:
        await get_redis().set(
            _brief_key(chat_id),
            json.dumps(payload, ensure_ascii=False),
            ex=STASH_TTL_SECONDS,
        )
    except Exception:  # noqa: BLE001 — the scene answers with a hint
        logger.warning("brief stash write failed", exc_info=True)


async def load_brief(chat_id: int) -> BriefEntry | None:
    """Return the stored brief and photos, or None on absence/expiry."""
    try:
        raw = await get_redis().get(_brief_key(chat_id))
    except Exception:  # noqa: BLE001 — the job degrades to the SEO-only path
        logger.warning("brief stash read failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("brief"), str):
        return None
    return BriefEntry(brief=data["brief"], photos=_decode_photos(data.get("photos")))


async def load_stashed_seo(chat_id: int) -> dict[str, Any] | None:
    """Return the stored report only, or None when absent/expired."""
    entry = await load_stashed_entry(chat_id)
    return entry.seo if entry is not None else None
