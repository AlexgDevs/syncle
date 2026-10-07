"""Niche search on Wildberries via a real browser (issue #39).

Wildberries answers plain-HTTP search clients with 403 and the rotating
proxy is dead (docs/adr/ADR-004), so the documented fallback is the
rendered search page: the SPA calls ``__internal/u-search/...`` itself
and this searcher intercepts that response from the network log.

Reuses the browser scraping settings (``PRICE_*``, ``PROXY_URL``) that
serve ``WbPriceSource`` — one shared level-3 escalation config.
"""

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from src.core.settings import get_settings
from src.modules.analytics.errors import NicheSearchError
from src.modules.analytics.parsers.browser import BrowserUnavailable, wb_browser_session
from src.modules.analytics.parsers.coerce import as_float, as_int, as_str
from src.modules.analytics.parsers.constants import WB_ORIGIN, wb_product_url
from src.modules.analytics.schemas import NicheItem

logger = logging.getLogger(__name__)

_SEARCH_PATH = "/catalog/0/search.aspx?search="
_U_SEARCH_MARKER = "__internal/u-search"
_POLL_INTERVAL = 0.5


class WbSearcher:
    """Collects WB listing items through a fresh browser session."""

    async def search(self, query: str, limit: int) -> list[NicheItem]:
        cfg = get_settings()
        if not cfg.PRICE_ENABLED:
            raise NicheSearchError("Browser scraping is disabled by settings.")
        timeout_ms = int(cfg.PRICE_TIMEOUT * 1000)
        try:
            async with wb_browser_session() as page:
                return await self._collect(page, query, limit, timeout_ms)
        except NicheSearchError:
            raise
        except BrowserUnavailable as exc:
            raise NicheSearchError(str(exc)) from exc
        except Exception as exc:
            raise NicheSearchError("Wildberries search session failed.") from exc

    async def _collect(
        self, page: Any, query: str, limit: int, timeout_ms: int
    ) -> list[NicheItem]:
        hit: dict[str, Any] = {}

        def on_response(response: Any) -> None:
            if _U_SEARCH_MARKER not in response.url or "/search" not in response.url:
                return
            if hit:
                return
            asyncio.ensure_future(self._capture(response, hit))

        page.on("response", on_response)
        url = f"{WB_ORIGIN}{_SEARCH_PATH}{quote(query)}"
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1000
        while not hit and loop.time() < deadline:
            await asyncio.sleep(_POLL_INTERVAL)
        products = hit.get("products")
        if not isinstance(products, list):
            raise NicheSearchError("Wildberries search page returned no listing data.")
        items = build_items(products, limit)
        logger.info("wb niche search %r -> %d items", query, len(items))
        return items

    @staticmethod
    async def _capture(response: Any, hit: dict[str, Any]) -> None:
        try:
            body = await response.text()
        except Exception:
            return
        if '"products"' not in body:
            return
        try:
            data = json.loads(body)
        except ValueError:
            return
        products = data.get("products")
        if not isinstance(products, list) or not products:
            return
        hit["products"] = products


def build_items(products: list[Any], limit: int) -> list[NicheItem]:
    """Maps raw WB search products to niche items (prices are kopecks)."""
    items: list[NicheItem] = []
    for raw in products:
        if len(items) >= limit:
            break
        if not isinstance(raw, dict):
            continue
        item_id = raw.get("id")
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            continue
        items.append(
            NicheItem(
                source=wb_product_url(item_id),
                title=as_str(raw.get("name")),
                brand=as_str(raw.get("brand")),
                price=_price(raw),
                rating=as_float(raw.get("reviewRating")),
                feedbacks_count=as_int(raw.get("feedbacks")),
            )
        )
    return items


def _price(product: dict[str, Any]) -> Decimal | None:
    sizes = product.get("sizes")
    if not isinstance(sizes, list) or not sizes:
        return None
    first = sizes[0]
    if not isinstance(first, dict):
        return None
    price = first.get("price")
    if not isinstance(price, dict):
        return None
    kopecks = price.get("product")
    if isinstance(kopecks, bool) or not isinstance(kopecks, int):
        return None
    value = Decimal(kopecks) / 100
    return value if value > 0 else None
