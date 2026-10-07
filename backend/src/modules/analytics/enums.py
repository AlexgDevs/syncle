"""Analytics enumerations."""

from enum import StrEnum


class Axis(StrEnum):
    PRICE = "price"
    KEYWORDS = "keywords"
    RATING = "rating"


class Stance(StrEnum):
    AHEAD = "ahead"
    BEHIND = "behind"
    EVEN = "even"
    UNKNOWN = "unknown"
