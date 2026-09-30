import asyncio
import json
from functools import lru_cache
from urllib.parse import urlparse

import httpx

from src.core.llm import LLMError, LLMProvider, get_llm_provider
from src.modules.analytics.errors import CardParseError, UnsupportedMarketplaceError
from src.modules.analytics.parsers import CardParser, WbParser
from src.modules.analytics.prompts import COMPARISON_SYSTEM, build_comparison_prompt
from src.modules.analytics.schemas import AnalysisReport, CompetitorCard
from src.modules.analytics.seo_diff import missed_seo_keys

_MAX_WEAKNESSES = 5

# TODO(P07): price / optimal_price need a working price source
# (browser/proxy escalation spike); until then price stays None ("недоступна").


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


def _parse_weaknesses(raw: str) -> list[str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data.get("content_weaknesses") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [item.strip() for item in items if isinstance(item, str) and item.strip()][
        :_MAX_WEAKNESSES
    ]


class ExpressAnalysisService:
    def __init__(self, parser: CardParser, llm: LLMProvider | None = None) -> None:
        self.parser = parser
        self.llm = llm

    async def compare_cards(
        self, own_source: str | None, rival_source: str
    ) -> AnalysisReport:
        if own_source is None:
            own, rival = None, await self._fetch_card(rival_source)
        else:
            own, rival = await asyncio.gather(
                self._fetch_card(own_source),
                self._fetch_card(rival_source),
            )
        report = AnalysisReport(competitor=rival, own_card=own)
        if own is not None:
            report.missed_seo_keys = missed_seo_keys(own, rival)
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
                prompt, system=COMPARISON_SYSTEM, temperature=0.4
            )
        except LLMError:
            # TODO(F06): log with structured logging; report degrades to diff only.
            return []
        return _parse_weaknesses(raw)


def get_analytics_service() -> ExpressAnalysisService:
    return ExpressAnalysisService(
        parser=WbParser(_get_client()), llm=get_llm_provider()
    )
