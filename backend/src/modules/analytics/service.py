import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from urllib.parse import urlparse

from decimal import Decimal, ROUND_HALF_UP

import httpx

from src.core.llm import LLMError, LLMProvider, get_llm_provider
from src.core.settings import get_settings
from src.modules.analytics.errors import CardParseError, UnsupportedMarketplaceError
from src.modules.analytics.parsers import CardParser, WbParser, WbPriceSource
from src.modules.analytics.prompts import (
    COMPARISON_MAX_TOKENS,
    COMPARISON_SYSTEM,
    COMPARISON_TEMPERATURE,
    build_comparison_prompt,
)
from src.modules.analytics.schemas import AnalysisReport, CompetitorCard
from src.modules.analytics.seo_diff import missed_seo_keys
from src.modules.analytics.weakness import parse_weaknesses

logger = logging.getLogger(__name__)

_PRICE_QUANT = Decimal("0.01")


@lru_cache
def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        follow_redirects=True,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9",
        },
    )


def _detect_marketplace(source: str) -> str | None:
    value = source.strip()
    if value.isdigit():
        return "wb"
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc.lower()
    if "wildberries" in host or host.endswith(".wb.ru"):
        return "wb"
    if "ozon" in host:
        return "ozon"
    return None


def _optimal_price(competitor_price: Decimal | None) -> Decimal | None:
    """Heuristic: undercut the competitor by a configurable percent."""
    if competitor_price is None:
        return None
    pct = Decimal(str(get_settings().OPTIMAL_PRICE_UNDERCUT_PCT))
    optimal = competitor_price * (Decimal("1") - pct / Decimal("100"))
    optimal = optimal.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
    return optimal if optimal > 0 else None


class ExpressAnalysisService:
    def __init__(self, parser: CardParser, llm: LLMProvider | None = None) -> None:
        self.parser = parser
        self.llm = llm

    async def compare_cards(
        self,
        own_source: str | None,
        rival_source: str,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> AnalysisReport:
        async def progress(step: str) -> None:
            if on_progress is not None:
                await on_progress(step)

        await progress("parsing_cards")
        if own_source is None:
            own, rival = None, await self._fetch_card(rival_source)
        else:
            own, rival = await asyncio.gather(
                self._fetch_card(own_source),
                self._fetch_card(rival_source),
            )
        report = AnalysisReport(competitor=rival, own_card=own)
        report.optimal_price = _optimal_price(rival.price)
        if own is not None:
            report.missed_seo_keys = missed_seo_keys(own, rival)
            await progress("analyzing_content")
            report.content_weaknesses = await self._content_weaknesses(
                own, rival, report.missed_seo_keys
            )
        return report

    async def _fetch_card(self, source: str) -> CompetitorCard:
        marketplace = _detect_marketplace(source)
        if marketplace is None:
            raise CardParseError(
                f"Invalid or unsupported product source: {source.strip()!r}"
            )
        if marketplace != "wb":
            raise UnsupportedMarketplaceError(marketplace)
        return await self.parser.parse(source)

    async def _content_weaknesses(
        self, own: CompetitorCard, rival: CompetitorCard, missed_keys: list[str]
    ) -> list[str]:
        if self.llm is None:
            return []
        prompt = build_comparison_prompt(own, rival, missed_keys)
        try:
            raw = await self.llm.complete(
                prompt,
                system=COMPARISON_SYSTEM,
                temperature=COMPARISON_TEMPERATURE,
                max_tokens=COMPARISON_MAX_TOKENS,
            )
        except LLMError as exc:
            logger.warning("LLM narrative degraded: %s", type(exc).__name__)
            return []
        return parse_weaknesses(raw)


def get_analytics_service() -> ExpressAnalysisService:
    client = _get_client()
    return ExpressAnalysisService(
        parser=WbParser(client, price_source=WbPriceSource(client)),
        llm=get_llm_provider(),
    )
