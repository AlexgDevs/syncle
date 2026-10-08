"""Review fetching for a product source (issue #32).

Dispatches to the marketplace parsers owned by the analytics service
(WB/Ozon ``get_reviews``) and maps generic parser failures to the typed
``ReviewsFetchError``; product-not-found and browser errors keep their
existing typed mappings in the bot.
"""

from src.modules.analytics import get_analytics_service
from src.modules.analytics.errors import (
    CardNotFoundError,
    CardParseError,
    OzonBrowserError,
    UnsupportedMarketplaceError,
)
from src.modules.analytics.schemas import Review
from src.modules.reviews.errors import ReviewsFetchError

_PASSTHROUGH_ERRORS = (
    CardNotFoundError,
    OzonBrowserError,
    UnsupportedMarketplaceError,
)


async def fetch_reviews(source: str) -> list[Review]:
    """Return capped reviews for a WB/Ozon source (REVIEWS_CAP).

    Raises:
        ReviewsFetchError: marketplace reviews service failed.
        CardNotFoundError: product does not exist (typed passthrough).
        OzonBrowserError: Ozon CDP session is unavailable (passthrough).
    """
    try:
        return await get_analytics_service().fetch_reviews(source)
    except _PASSTHROUGH_ERRORS:
        raise
    except CardParseError as exc:
        raise ReviewsFetchError(f"Reviews fetch failed: {exc}") from exc
