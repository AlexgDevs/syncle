from src.modules.analytics.parsers.base import (
    CardParser,
    CardPriceSource,
    CardWithReviews,
    NicheSearcher,
    ReviewsSource,
)
from src.modules.analytics.parsers.ozon import OzonParser
from src.modules.analytics.parsers.ozon_search import OzonSearcher
from src.modules.analytics.parsers.wb import WbParser
from src.modules.analytics.parsers.wb_price import WbPriceSource
from src.modules.analytics.parsers.wb_search import WbSearcher

__all__ = [
    "CardParser",
    "CardPriceSource",
    "CardWithReviews",
    "NicheSearcher",
    "OzonParser",
    "OzonSearcher",
    "ReviewsSource",
    "WbParser",
    "WbPriceSource",
    "WbSearcher",
]
