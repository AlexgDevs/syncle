from urllib.parse import urlparse

import httpx

from src.modules.analytics.errors import CardParseError, UnsupportedMarketplaceError
from src.modules.analytics.parsers import CardParser, WbParser
from src.modules.analytics.schemas import AnalysisReport

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
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
    return _client


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


class ExpressAnalysisService:
    def __init__(self, parser: CardParser) -> None:
        self.parser = parser

    async def analyze_card(self, source: str) -> AnalysisReport:
        marketplace = _detect_marketplace(source)
        if marketplace is None:
            raise CardParseError(
                f"Invalid or unsupported product source: {source.strip()!r}"
            )
        if marketplace != "wb":
            raise UnsupportedMarketplaceError(marketplace)
        card = await self.parser.parse(source)
        return AnalysisReport(competitor=card)


def get_analytics_service() -> ExpressAnalysisService:
    return ExpressAnalysisService(parser=WbParser(_get_client()))
