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


class AnalysisReport(BaseModel):
    competitor: CompetitorCard
    own_card: CompetitorCard | None = None
    missed_seo_keys: list[str] = []
    content_weaknesses: list[str] = []
    positioning: list[PositioningInsight] = []
    # Undercut heuristic: competitor price minus OPTIMAL_PRICE_UNDERCUT_PCT.
    optimal_price: Decimal | None = None
