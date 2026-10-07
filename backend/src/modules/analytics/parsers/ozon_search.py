"""Niche search on Ozon via the composer API (issue #39).

Ozon rejects plain HTTP clients with a JS bot challenge, so listing
pages are fetched inside the shared Edge CDP session (``CdpJsonClient``).
Each search page (``tileGridDesktop`` widget) carries 8 items, so pages
are walked until the requested limit is reached.
"""

import json
import logging
import re
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from src.core.settings import get_settings
from src.modules.analytics.errors import NicheSearchError
from src.modules.analytics.parsers.cdp import CdpJsonClient
from src.modules.analytics.parsers.coerce import as_float, as_str, parse_price
from src.modules.analytics.parsers.constants import (
    OZON_ORIGIN,
    OZON_PAGE_API,
    ozon_product_url,
)
from src.modules.analytics.schemas import NicheItem

logger = logging.getLogger(__name__)

_MAX_PAGES = 10

# "4.8"-like rating strings must not be mistaken for review counts.
_FLOAT_RE = re.compile(r"\d+[.,]\d+")
_INT_RE = re.compile(r"\d[\d\s\u00a0\u2009]*")

# Badge texts that share the brand label list but are not brands.
_NON_BRAND_LABELS = frozenset(
    {
        "бренд проверен",
        "стало дешевле",
        "хит продаж",
        "озон",
        "ozon",
        "plus",
        "доставка сегодня",
    }
)


class OzonSearcher:
    """Collects Ozon listing items through the shared CDP session."""

    def __init__(self, client: CdpJsonClient | None = None) -> None:
        self._client = client or CdpJsonClient(get_settings().OZON_CDP_URL)

    async def search(self, query: str, limit: int) -> list[NicheItem]:
        items: list[NicheItem] = []
        page = 1
        while len(items) < limit and page <= _MAX_PAGES:
            path = f"/search?text={quote(query)}&from_global=true&page={page}"
            status, body = await self._client.fetch_text(
                OZON_PAGE_API + quote(path, safe="")
            )
            raw_items = self._tile_items(status, body)
            if not raw_items:
                break
            for raw in raw_items:
                if len(items) >= limit:
                    break
                item = _build_item(raw)
                if item is not None:
                    items.append(item)
            page += 1
        logger.info("ozon niche search %r -> %d items", query, len(items))
        return items

    @staticmethod
    def _tile_items(status: int, body: str) -> list[Any]:
        if status != 200:
            raise NicheSearchError(f"Ozon search responded with HTTP {status}.")
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise NicheSearchError("Ozon search returned a non-JSON response.") from exc
        if not isinstance(data, dict):
            raise NicheSearchError("Ozon search returned an unexpected payload.")
        states = data.get("widgetStates")
        if not isinstance(states, dict):
            return []
        for key, value in states.items():
            if not key.startswith("tileGridDesktop-"):
                continue
            if not isinstance(value, str):
                continue
            try:
                widget = json.loads(value)
            except ValueError:
                continue
            items = widget.get("items")
            if isinstance(items, list):
                return items
        return []


def _build_item(raw: Any) -> NicheItem | None:
    if not isinstance(raw, dict):
        return None
    sku = raw.get("sku") if not isinstance(raw.get("sku"), bool) else None
    source: str | None
    if isinstance(sku, int):
        source = ozon_product_url(sku)
    else:
        source = _link(raw.get("action"))
    if source is None:
        return None
    title = brand = None
    price: Decimal | None = None
    rating: float | None = None
    feedbacks: int | None = None
    states = raw.get("mainState")
    for entry in states if isinstance(states, list) else []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        if kind == "priceV2":
            price = _price(entry.get("priceV2"))
        elif kind == "textDS" and entry.get("id") == "name":
            title = as_str((entry.get("textDS") or {}).get("text"))
        elif kind == "labelListV2":
            widget = entry.get("labelListV2") or {}
            texts = _label_texts(widget)
            automation = _automation_id(widget)
            if automation == "tile-list-labels" and texts:
                brand = _brand(texts)
            elif automation == "tile-list-rating":
                rating, feedbacks = _rating_feedbacks(texts)
    return NicheItem(
        source=source,
        title=title,
        brand=brand,
        price=price,
        rating=rating,
        feedbacks_count=feedbacks,
    )


def _link(action: Any) -> str | None:
    if not isinstance(action, dict):
        return None
    link = action.get("link")
    if not isinstance(link, str) or not link:
        return None
    return OZON_ORIGIN + link.split("?")[0]


def _brand(texts: list[str]) -> str | None:
    """First label that is not a badge (e.g. 'Бренд проверен')."""
    for text in texts:
        if text.lower() not in _NON_BRAND_LABELS:
            return as_str(text)
    return None


def _automation_id(widget: dict[str, Any]) -> str | None:
    tracking = widget.get("testInfo")
    if not isinstance(tracking, dict):
        return None
    value = tracking.get("automatizationId")
    return value if isinstance(value, str) else None


def _label_texts(widget: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    entries = widget.get("items")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("type") != "text":
            continue
        text = as_str((entry.get("text") or {}).get("text"))
        if text:
            texts.append(text)
    return texts


def _rating_feedbacks(texts: list[str]) -> tuple[float | None, int | None]:
    rating: float | None = None
    feedbacks: int | None = None
    for text in texts:
        cleaned = text.replace("\xa0", " ").replace("\u2009", " ").strip()
        if rating is None and "." in cleaned:
            rating = as_float(cleaned)
            if rating is not None:
                continue
        if feedbacks is None and not _FLOAT_RE.fullmatch(cleaned):
            match = _INT_RE.search(cleaned)
            if match is not None:
                digits = re.sub(r"\D", "", match.group(0))
                feedbacks = int(digits) if digits else None
    return rating, feedbacks


def _price(widget: dict[str, Any] | None) -> Decimal | None:
    if not isinstance(widget, dict):
        return None
    entries = widget.get("price")
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("textStyle") != "PRICE":
            continue
        return parse_price(entry.get("text"))
    return None
