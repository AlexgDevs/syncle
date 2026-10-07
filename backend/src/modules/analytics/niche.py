"""Pure aggregation of niche listing items (issue #41).

No I/O here: the functions take the items collected by a searcher and
return display-ready statistics for the report and the LLM prompt.
"""

import json
import re
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

from src.modules.analytics.schemas import (
    BrandShare,
    FeedbackBand,
    NicheItem,
    NicheStats,
    PriceBand,
    WordCount,
)

_BRAND_TOP = 10
_WORDS_TOP = 15
_MAX_INSIGHTS = 6
_MIN_WORD_LEN = 3
_PRICE_BAND_COUNT = 5
_PRICE_QUANT = Decimal("0.01")
_WORD_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

# Fixed review-count intervals: (low, high); high None = open-ended.
_FEEDBACK_EDGES = ((0, 0), (1, 10), (11, 100), (101, 1000), (1001, None))

_STOP_WORDS = frozenset(
    {
        # Russian
        "без",
        "более",
        "был",
        "быть",
        "вам",
        "вас",
        "вдруг",
        "ведь",
        "вот",
        "все",
        "всего",
        "вы",
        "где",
        "год",
        "да",
        "даже",
        "для",
        "до",
        "его",
        "ее",
        "если",
        "еще",
        "же",
        "за",
        "и",
        "из",
        "или",
        "им",
        "их",
        "к",
        "как",
        "какая",
        "какой",
        "когда",
        "конечно",
        "кто",
        "куда",
        "ли",
        "лучше",
        "между",
        "меня",
        "мне",
        "много",
        "мог",
        "мой",
        "мочь",
        "на",
        "над",
        "надо",
        "наконец",
        "наш",
        "не",
        "него",
        "нее",
        "нет",
        "ни",
        "нибудь",
        "никогда",
        "ним",
        "них",
        "но",
        "новый",
        "нужно",
        "о",
        "об",
        "один",
        "он",
        "она",
        "они",
        "оно",
        "опять",
        "от",
        "перед",
        "по",
        "под",
        "после",
        "потом",
        "потому",
        "почему",
        "при",
        "про",
        "раз",
        "разве",
        "с",
        "сам",
        "свое",
        "себе",
        "себя",
        "сегодня",
        "сейчас",
        "сказал",
        "сколько",
        "со",
        "совсем",
        "стал",
        "стать",
        "так",
        "такой",
        "там",
        "тебя",
        "тем",
        "теперь",
        "то",
        "тогда",
        "того",
        "тоже",
        "только",
        "том",
        "тот",
        "три",
        "тут",
        "ты",
        "у",
        "уже",
        "хорошо",
        "хоть",
        "чего",
        "человек",
        "чем",
        "через",
        "что",
        "чтоб",
        "чтобы",
        "чуть",
        "эта",
        "эти",
        "это",
        "этого",
        "этой",
        "этом",
        "этот",
        "эту",
        "я",
        # English / numbers commonly seen in titles
        "the",
        "and",
        "for",
        "with",
        "from",
        "new",
        "pro",
        "plus",
        "set",
        "mm",
        "sm",
        "kg",
    }
)


def build_niche_stats(items: list[NicheItem]) -> NicheStats:
    """Aggregates listing items into report statistics (issue #41)."""
    total = len(items)
    prices = [i.price for i in items if i.price is not None]
    ratings = [i.rating for i in items if i.rating is not None]
    feedbacks = [i.feedbacks_count for i in items if i.feedbacks_count is not None]
    brands = Counter(i.brand for i in items if i.brand is not None and i.brand.strip())
    words = Counter(
        word.lower()
        for i in items
        if i.title is not None
        for word in _WORD_RE.findall(i.title)
        if len(word) >= _MIN_WORD_LEN and word.lower() not in _STOP_WORDS
    )
    return NicheStats(
        total_items=total,
        price_coverage=round(len(prices) / total, 3) if total else 0.0,
        price_min=min(prices) if prices else None,
        price_max=max(prices) if prices else None,
        price_avg=_avg(prices),
        price_bands=_price_bands(prices),
        brand_mix=[
            BrandShare(brand=brand, count=count)
            for brand, count in brands.most_common(_BRAND_TOP)
        ],
        rating_avg=(round(sum(ratings) / len(ratings), 2) if ratings else None),
        rating_count=len(ratings),
        feedbacks_total=sum(feedbacks),
        feedbacks_max=max(feedbacks) if feedbacks else None,
        feedback_bands=_feedback_bands(feedbacks),
        top_title_words=[
            WordCount(word=word, count=count)
            for word, count in words.most_common(_WORDS_TOP)
        ],
    )


def _price_bands(prices: list[Decimal]) -> list[PriceBand]:
    """Equal-width price intervals ``[low, high)`` (last band inclusive)."""
    if not prices:
        return []
    low, high = min(prices), max(prices)
    if low == high:
        return [PriceBand(low=low, high=high, count=len(prices))]
    step = (high - low) / _PRICE_BAND_COUNT
    counts = [0] * _PRICE_BAND_COUNT
    for price in prices:
        index = int((price - low) / step)
        counts[min(index, _PRICE_BAND_COUNT - 1)] += 1
    bands: list[PriceBand] = []
    for index, count in enumerate(counts):
        band_low = (low + step * index).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
        if index == _PRICE_BAND_COUNT - 1:
            bands.append(PriceBand(low=band_low, high=high, count=count))
        else:
            band_high = (low + step * (index + 1)).quantize(
                _PRICE_QUANT, rounding=ROUND_HALF_UP
            )
            bands.append(PriceBand(low=band_low, high=band_high, count=count))
    return bands


def _feedback_bands(feedbacks: list[int]) -> list[FeedbackBand]:
    """Fixed review-count intervals; empty bands are dropped."""
    if not feedbacks:
        return []
    bands: list[FeedbackBand] = []
    for low, high in _FEEDBACK_EDGES:
        count = sum(
            1 for value in feedbacks if value >= low and (high is None or value <= high)
        )
        if count:
            bands.append(FeedbackBand(low=low, high=high, count=count))
    return bands


def _avg(prices: list[Decimal]) -> Decimal | None:
    if not prices:
        return None
    value = sum(prices) / Decimal(len(prices))
    return value.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)


def parse_insights(raw: str) -> list[str]:
    """Parses the niche LLM output into insight bullets (issue #42).

    Degrades to an empty list on any malformed payload — the report then
    renders without the narrative block.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data.get("insights") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    insights: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if cleaned:
            insights.append(cleaned)
        if len(insights) >= _MAX_INSIGHTS:
            break
    return insights
