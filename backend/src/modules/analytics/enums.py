"""Analytics enumerations."""

from enum import StrEnum


class Marketplace(StrEnum):
    WB = "wb"
    OZON = "ozon"


class Axis(StrEnum):
    PRICE = "price"
    KEYWORDS = "keywords"
    RATING = "rating"


class Stance(StrEnum):
    AHEAD = "ahead"
    BEHIND = "behind"
    EVEN = "even"
    UNKNOWN = "unknown"


MARKETPLACES: tuple[Marketplace, ...] = (Marketplace.WB, Marketplace.OZON)

MARKETPLACE_TITLES: dict[str, str] = {
    Marketplace.WB: "Wildberries",
    Marketplace.OZON: "Ozon",
}
