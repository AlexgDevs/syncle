from typing import Protocol

from src.modules.analytics.schemas import CompetitorCard


class CardParser(Protocol):
    """Parses a marketplace product source (URL or article) into a card."""

    async def parse(self, source: str) -> CompetitorCard: ...
