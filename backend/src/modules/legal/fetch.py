"""Card fetching for the legal scanner (issue #59).

Thin adapter over the analytics card parsers (WB/Ozon), mirroring the
reviews fetch module: generic parser failures become the typed
``LegalScanError`` while product-not-found and browser errors keep
their existing typed mappings in the bot.
"""

from src.modules.analytics import get_analytics_service
from src.modules.analytics.errors import (
    CardNotFoundError,
    CardParseError,
    OzonBrowserError,
    UnsupportedMarketplaceError,
)
from src.modules.analytics.schemas import CompetitorCard
from src.modules.legal.errors import LegalScanError

_PASSTHROUGH_ERRORS = (
    CardNotFoundError,
    OzonBrowserError,
    UnsupportedMarketplaceError,
)


async def fetch_card(source: str) -> CompetitorCard:
    """Return one parsed card for a WB/Ozon source (#59).

    Raises:
        LegalScanError: marketplace parser failed.
        CardNotFoundError: product does not exist (typed passthrough).
        OzonBrowserError: Ozon CDP session is unavailable (passthrough).
    """
    try:
        return await get_analytics_service().fetch_card(source)
    except _PASSTHROUGH_ERRORS:
        raise
    except CardParseError as exc:
        raise LegalScanError(f"Card fetch failed: {exc}") from exc
