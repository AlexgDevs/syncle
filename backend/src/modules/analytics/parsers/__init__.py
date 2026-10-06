from src.modules.analytics.parsers.base import (
    CardParser,
    CardPriceSource,
    ReviewsSource,
)
from src.modules.analytics.parsers.ozon import OzonParser
from src.modules.analytics.parsers.wb import WbParser
from src.modules.analytics.parsers.wb_price import WbPriceSource

__all__ = [
    "CardParser",
    "CardPriceSource",
    "OzonParser",
    "ReviewsSource",
    "WbParser",
    "WbPriceSource",
]
