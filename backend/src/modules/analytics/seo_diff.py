"""Deterministic SEO-key diff (no LLM)."""

import re

from src.modules.analytics.schemas import CompetitorCard

_WORD_RE = re.compile(r"[а-яёa-z0-9]{3,}", re.IGNORECASE)
MAX_MISSED_KEYS = 12

# Common filler words that carry no SEO value (>=3 chars only).
_STOPWORDS = frozenset(
    {
        "для",
        "это",
        "как",
        "его",
        "наш",
        "ваш",
        "так",
        "или",
        "либо",
        "что",
        "все",
        "всё",
        "про",
        "них",
        "неё",
        "ней",
        "мне",
        "тебе",
        "само",
        "сама",
        "сами",
        "очень",
        "также",
        "можно",
        "который",
        "которая",
        "которые",
        "после",
        "перед",
        "через",
        "без",
        "меж",
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "were",
        "has",
        "have",
        "not",
        "you",
        "your",
        "our",
        "its",
        "their",
    }
)


def extract_keys(card: CompetitorCard) -> list[str]:
    """Ordered unique tokens from a card title and description."""
    text = " ".join(part for part in (card.title, card.description) if part)
    keys: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(text):
        token = match.group(0).lower()
        if token in _STOPWORDS or token in seen:
            continue
        seen.add(token)
        keys.append(token)
    return keys


def missed_seo_keys(own: CompetitorCard, rival: CompetitorCard) -> list[str]:
    """SEO keys present on the rival card but missing from ours."""
    own_keys = set(extract_keys(own))
    missed = [key for key in extract_keys(rival) if key not in own_keys]
    return missed[:MAX_MISSED_KEYS]
