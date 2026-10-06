from decimal import Decimal
from typing import Protocol

from src.modules.analytics.schemas import CompetitorCard, Review


class CardParser(Protocol):
    """Parses a marketplace product source (URL or article) into a card."""

    async def parse(self, source: str) -> CompetitorCard: ...


class ReviewsSource(Protocol):
    """Extracts reviews for a marketplace product source.

    Reviews are capped by settings (``REVIEWS_CAP``): WB returns a single
    batch per request (query pagination is ignored by the endpoint), so the
    cap is applied client-side.
    """

    async def get_reviews(self, source: str) -> list[Review]: ...


class CardPriceSource(Protocol):
    """Resolves the current price of a product by marketplace article.

    Returns None when the price is unavailable (source blocked, disabled
    by settings, or parsing failed) — callers degrade to "price: None".
    """

    async def fetch_price(self, nm: int) -> Decimal | None: ...
