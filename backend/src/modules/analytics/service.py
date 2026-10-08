import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache

from decimal import Decimal, ROUND_HALF_UP

from src.core.http import get_client
from src.core.llm import LLMError, LLMProvider, get_llm_provider
from src.core.settings import get_settings
from src.modules.analytics.enums import Marketplace
from src.modules.analytics.errors import CardParseError, UnsupportedMarketplaceError
from src.modules.analytics.niche import build_niche_stats, parse_insights
from src.modules.analytics.parsers import (
    CardWithReviews,
    NicheSearcher,
    OzonParser,
    OzonSearcher,
    WbParser,
    WbPriceSource,
    WbSearcher,
)
from src.modules.analytics.parsers.source import parse_source
from src.modules.analytics.prompts import (
    COMPARISON_MAX_TOKENS,
    COMPARISON_SYSTEM,
    COMPARISON_TEMPERATURE,
    NICHE_MAX_TOKENS,
    NICHE_SYSTEM,
    NICHE_TEMPERATURE,
    build_comparison_prompt,
    build_niche_prompt,
)
from src.modules.analytics.schemas import (
    AnalysisReport,
    CompetitorCard,
    NicheReport,
    NicheStats,
    Review,
)
from src.modules.analytics.recommendations import positioning_recommendations
from src.modules.analytics.seo_diff import missed_seo_keys
from src.modules.analytics.weakness import parse_weaknesses

logger = logging.getLogger(__name__)

_PRICE_QUANT = Decimal("0.01")


def _detect_marketplace(source: str) -> Marketplace | None:
    _, parsed = parse_source(source)
    if parsed is None:
        return Marketplace.WB
    host = parsed.netloc.lower()
    if "wildberries" in host or host.endswith(".wb.ru"):
        return Marketplace.WB
    if "ozon" in host:
        return Marketplace.OZON
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
    def __init__(
        self,
        parser: CardWithReviews,
        llm: LLMProvider | None = None,
        ozon_parser: CardWithReviews | None = None,
        wb_searcher: NicheSearcher | None = None,
        ozon_searcher: NicheSearcher | None = None,
    ) -> None:
        self.parser = parser
        self.llm = llm
        self._ozon_parser = ozon_parser
        self._wb_searcher = wb_searcher
        self._ozon_searcher = ozon_searcher

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
            report.positioning = positioning_recommendations(
                own, rival, report.missed_seo_keys
            )
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
        if marketplace is Marketplace.OZON:
            if self._ozon_parser is None:
                self._ozon_parser = OzonParser()
            return await self._ozon_parser.parse(source)
        if marketplace is not Marketplace.WB:
            raise UnsupportedMarketplaceError(str(marketplace))
        return await self.parser.parse(source)

    async def fetch_reviews(self, source: str) -> list[Review]:
        """Reviews of one source via the matching marketplace parser (#32).

        The cap (``REVIEWS_CAP``) is applied inside the parsers.
        """
        marketplace = _detect_marketplace(source)
        if marketplace is None:
            raise CardParseError(
                f"Invalid or unsupported product source: {source.strip()!r}"
            )
        if marketplace is Marketplace.OZON:
            if self._ozon_parser is None:
                self._ozon_parser = OzonParser()
            return await self._ozon_parser.get_reviews(source)
        if marketplace is not Marketplace.WB:
            raise UnsupportedMarketplaceError(str(marketplace))
        return await self.parser.get_reviews(source)

    async def scan_niche(
        self,
        marketplace: str,
        query: str,
        own_source: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> NicheReport:
        """Deep niche scan (issues #39..#42): search, aggregate, narrate.

        The listing comes from a single search request per marketplace —
        per-item price/card fetches are deliberately avoided (seconds per
        item). A failing optional own card degrades to a niche-only
        narrative instead of aborting the job.
        """

        async def progress(step: str) -> None:
            if on_progress is not None:
                await on_progress(step)

        searcher = self._niche_searcher(marketplace)
        await progress("searching_niche")
        items = await searcher.search(query, get_settings().NICHE_ITEM_CAP)
        stats = build_niche_stats(items)
        own: CompetitorCard | None = None
        if own_source is not None:
            await progress("parsing_cards")
            try:
                own = await self._fetch_card(own_source)
            except CardParseError as exc:
                logger.warning("niche own card degraded: %s", type(exc).__name__)
        await progress("analyzing_niche")
        insights = await self._niche_insights(query, marketplace, stats, own)
        return NicheReport(
            query=query,
            marketplace=marketplace,
            stats=stats,
            insights=insights,
        )

    def _niche_searcher(self, marketplace: str) -> NicheSearcher:
        if marketplace == Marketplace.WB:
            if self._wb_searcher is None:
                self._wb_searcher = WbSearcher()
            return self._wb_searcher
        if marketplace == Marketplace.OZON:
            if self._ozon_searcher is None:
                self._ozon_searcher = OzonSearcher()
            return self._ozon_searcher
        raise UnsupportedMarketplaceError(marketplace)

    async def _niche_insights(
        self,
        query: str,
        marketplace: str,
        stats: NicheStats,
        own: CompetitorCard | None,
    ) -> list[str]:
        if self.llm is None or stats.total_items == 0:
            return []
        prompt = build_niche_prompt(query, marketplace, stats, own)
        try:
            raw = await self.llm.complete(
                prompt,
                system=NICHE_SYSTEM,
                temperature=NICHE_TEMPERATURE,
                max_tokens=NICHE_MAX_TOKENS,
            )
        except LLMError as exc:
            logger.warning("LLM niche narrative degraded: %s", type(exc).__name__)
            return []
        return parse_insights(raw)

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


@lru_cache
def get_analytics_service() -> ExpressAnalysisService:
    """Process-wide singleton: adapters share parsers and the CDP session."""
    return ExpressAnalysisService(
        parser=WbParser(
            get_client("basket"),
            price_source=WbPriceSource(get_client("basket")),
            feedbacks_client=get_client("feedbacks"),
        ),
        llm=get_llm_provider(),
        wb_searcher=WbSearcher(),
        ozon_searcher=OzonSearcher(),
    )
