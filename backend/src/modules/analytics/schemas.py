from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from src.modules.analytics.enums import Axis, Stance


class CompetitorCard(BaseModel):
    source: str
    title: str | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    price: Decimal | None = None
    rating: float | None = None
    feedbacks_count: int | None = None


class Review(BaseModel):
    """A single marketplace review.

    Best effort: every field except ``review_id`` may be None when the
    marketplace omits it or sends an unexpected value.
    """

    review_id: str
    text: str | None = None
    pros: str | None = None
    cons: str | None = None
    rating: int | None = None
    date: datetime | None = None
    author: str | None = None


class PositioningInsight(BaseModel):
    """One comparison axis of the positioning block (issue #36).

    Values are display-ready numbers (price, rating, keyword counts);
    user-facing phrasing lives in the bot renderer.
    """

    axis: Axis
    stance: Stance
    own_value: str | None = None
    rival_value: str | None = None
    missed_count: int | None = None
    exclusive_count: int | None = None


class NicheItem(BaseModel):
    """One marketplace listing item found by a niche search (issue #39).

    Best effort: every field except ``source`` may be None when the
    listing omits it (prices come from the search payload only, see
    ``price_coverage`` in the niche stats).
    """

    source: str  # product URL or article, unique per marketplace
    title: str | None = None
    brand: str | None = None
    price: Decimal | None = None
    rating: float | None = None
    feedbacks_count: int | None = None


class BrandShare(BaseModel):
    """Brand occurrence count within the scanned niche slice."""

    brand: str
    count: int


class WordCount(BaseModel):
    """Title keyword occurrence count within the scanned niche slice."""

    word: str
    count: int


class PriceBand(BaseModel):
    """Items count inside one price interval of the niche slice."""

    low: Decimal
    high: Decimal | None = None  # None = open-ended top band
    count: int


class FeedbackBand(BaseModel):
    """Items count inside one review-count interval of the niche slice."""

    low: int
    high: int | None = None  # None = open-ended top band
    count: int


class NicheStats(BaseModel):
    """Aggregated metrics over a niche listing slice (issue #41)."""

    total_items: int
    price_coverage: float  # share of items carrying a price (0..1)
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    price_avg: Decimal | None = None
    price_bands: list[PriceBand] = []
    brand_mix: list[BrandShare] = []
    rating_avg: float | None = None
    rating_count: int = 0  # items carrying a rating
    feedbacks_total: int = 0
    feedbacks_max: int | None = None
    feedback_bands: list[FeedbackBand] = []
    top_title_words: list[WordCount] = []


class NicheReport(BaseModel):
    """Deep niche scan result (issues #41..#44).

    Insights are LLM-generated Russian bullets; an empty list means the
    LLM narrative degraded — the stats block still renders on its own.
    """

    query: str
    marketplace: str  # "wb" | "ozon"
    stats: NicheStats
    insights: list[str] = []


class AnalysisReport(BaseModel):
    competitor: CompetitorCard
    own_card: CompetitorCard | None = None
    missed_seo_keys: list[str] = []
    content_weaknesses: list[str] = []
    positioning: list[PositioningInsight] = []
    # Undercut heuristic: competitor price minus OPTIMAL_PRICE_UNDERCUT_PCT.
    optimal_price: Decimal | None = None
