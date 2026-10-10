"""Telegram photo download helpers (issues #27, #62)."""

import io

from aiogram import Bot

PHOTO_CAP = 3  # shared cap for the SEO (#27) and infographics (#62) scenes


def clean_file_ids(raw: object) -> list[str]:
    """FSM blob -> file_id list (non-string entries dropped)."""
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    return []


def append_photo_id(file_ids: list[str], file_id: str) -> list[str] | None:
    """Return the list with file_id appended, or None past PHOTO_CAP."""
    if len(file_ids) >= PHOTO_CAP:
        return None
    return [*file_ids, file_id]


async def download_photos(bot: Bot, file_ids: list[str]) -> list[bytes]:
    """Download Telegram files as raw bytes, in order."""
    images: list[bytes] = []
    for file_id in file_ids:
        file = await bot.get_file(file_id)
        buffer = io.BytesIO()
        await bot.download(file, destination=buffer)
        images.append(buffer.getvalue())
    return images
