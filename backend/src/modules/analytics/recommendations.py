"""Deterministic positioning recommendations (issue #36).

Compares own and rival cards along three axes — price, SEO keywords
and rating — and reports where we win, lose, or lack data. Pure
computation with no LLM: every verdict derives from card fields that
are already fetched, so the block never invents statistics.
"""

from src.modules.analytics.enums import Axis, Stance
from src.modules.analytics.schemas import CompetitorCard, PositioningInsight
from src.modules.analytics.seo_diff import extract_keys


def _price_insight(own: CompetitorCard, rival: CompetitorCard) -> PositioningInsight:
    if own.price is None or rival.price is None:
        return PositioningInsight(axis=Axis.PRICE, stance=Stance.UNKNOWN)
    if own.price < rival.price:
        stance = Stance.AHEAD
    elif own.price > rival.price:
        stance = Stance.BEHIND
    else:
        stance = Stance.EVEN
    return PositioningInsight(
        axis=Axis.PRICE,
        stance=stance,
        own_value=str(own.price),
        rival_value=str(rival.price),
    )


def _keywords_insight(
    own: CompetitorCard,
    rival: CompetitorCard,
    missed_keys: list[str],
) -> PositioningInsight:
    own_keys = set(extract_keys(own))
    rival_keys = set(extract_keys(rival))
    exclusive = [key for key in extract_keys(own) if key not in rival_keys]
    if missed_keys:
        stance = Stance.BEHIND
    elif exclusive:
        stance = Stance.AHEAD
    else:
        stance = Stance.EVEN
    return PositioningInsight(
        axis=Axis.KEYWORDS,
        stance=stance,
        missed_count=len(missed_keys),
        exclusive_count=len(exclusive),
    )


def _rating_insight(own: CompetitorCard, rival: CompetitorCard) -> PositioningInsight:
    if own.rating is None or rival.rating is None:
        return PositioningInsight(axis=Axis.RATING, stance=Stance.UNKNOWN)
    if own.rating > rival.rating:
        stance = Stance.AHEAD
    elif own.rating < rival.rating:
        stance = Stance.BEHIND
    else:
        stance = Stance.EVEN
    return PositioningInsight(
        axis=Axis.RATING,
        stance=stance,
        own_value=str(own.rating),
        rival_value=str(rival.rating),
    )


def positioning_recommendations(
    own: CompetitorCard,
    rival: CompetitorCard,
    missed_keys: list[str],
) -> list[PositioningInsight]:
    """Returns the positioning block for an own/rival pair.

    ``missed_keys`` must be the already computed SEO diff
    (``seo_diff.missed_seo_keys``) so both the report and this block
    show the same numbers.
    """
    return [
        _price_insight(own, rival),
        _keywords_insight(own, rival, missed_keys),
        _rating_insight(own, rival),
    ]
