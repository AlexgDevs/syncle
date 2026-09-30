"""Price parsing via a real browser (Playwright).

Level-3 price escalation per docs/adr/ADR-004: Wildberries serves an
anti-bot JS challenge (498) to plain HTTP clients and blocks API hosts
(403), so the only working source is the rendered catalog page.

Price sources, in order:
1. the page <title> ("... купить за 4 907 ₽ ...") — the SPA writes the
   plain price there for most cards;
2. the first price in the rendered body text (the purchase panel) —
   some cards have a title without a price.

Both degrade to None when the product page is missing or empty.
"""

import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from src.core.settings import get_settings

logger = logging.getLogger(__name__)

_TITLE_PRICE = re.compile(r"за\s+([\d][\d\s\xa0]*?)\s*₽")
_BODY_PRICE = re.compile(r"(\d[\d\s\xa0]{1,15})\s*₽")
_NOT_FOUND = "ничего не найдено"
# Never read prices below recommendation feeds: for out-of-stock cards the
# purchase panel has no price, and the first ruble amount would belong to
# an unrelated product block.
_BODY_CUT_MARKERS = (
    "Хит продаж",
    "Рекомендуем",
    "С этим покупают",
    "Вы смотрели",
    "Похожие товары",
    "Недавно смотрели",
)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)
_HIDE_WEBDRIVER = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
)
_POLL_INTERVAL = 1.0
# If the SPA did not open the product card within this window, treat the
# product as missing instead of burning the full price timeout.
_NOT_FOUND_AFTER = 15.0


def _to_price(raw: str) -> Decimal | None:
    digits = re.sub(r"[\s\xa0]", "", raw)
    try:
        price = Decimal(digits)
    except InvalidOperation:
        return None
    return price if price > 0 else None


def parse_title_price(title: str) -> Decimal | None:
    match = _TITLE_PRICE.search(title)
    if match is None:
        return None
    return _to_price(match.group(1))


def parse_body_price(text: str) -> Decimal | None:
    """First ruble amount in the purchase panel area of the page."""
    for marker in _BODY_CUT_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
    for match in _BODY_PRICE.finditer(text):
        price = _to_price(match.group(1))
        if price is not None:
            return price
    return None


def _is_product_title(title: str) -> bool:
    """True when the SPA opened a product card (title invites to buy)."""
    return "купить" in title.lower()


def _is_idle_title(title: str) -> bool:
    """True while the page shows a non-product fallback (e.g. the homepage)."""
    if not title or title == "..." or title.startswith("Loading"):
        return True
    lowered = title.lower()
    if "купить" in lowered:
        return False
    return "wildberries" in lowered


class WbPriceSource:
    """Browser-backed price source; degrades to None on any failure."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_price(self, nm: int) -> Decimal | None:
        cfg = get_settings()
        if not cfg.PRICE_ENABLED:
            return None
        price = await self._fetch_once(nm)
        if price is None and cfg.PROXY_ROTATE_URL and cfg.PROXY_URL:
            await self._rotate_ip()
            price = await self._fetch_once(nm)
        return price

    async def _fetch_once(self, nm: int) -> Decimal | None:
        cfg = get_settings()
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("playwright is not installed; price unavailable")
            return None
        timeout_ms = int(cfg.PRICE_TIMEOUT * 1000)
        try:
            async with async_playwright() as playwright:
                launch_kwargs: dict[str, Any] = {"headless": cfg.PRICE_HEADLESS}
                if cfg.PROXY_URL:
                    launch_kwargs["proxy"] = {"server": cfg.PROXY_URL}
                browser = await playwright.chromium.launch(**launch_kwargs)
                try:
                    context = await browser.new_context(
                        locale="ru-RU",
                        timezone_id="Europe/Moscow",
                        user_agent=_USER_AGENT,
                        viewport={"width": 1440, "height": 1000},
                    )
                    await context.add_init_script(_HIDE_WEBDRIVER)
                    page = await context.new_page()
                    await page.goto(
                        f"https://www.wildberries.ru/catalog/{nm}/detail.aspx",
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    return await self._wait_price(page, nm, timeout_ms)
                finally:
                    await browser.close()
        except Exception as exc:
            logger.warning("price fetch failed for nm=%s: %s", nm, type(exc).__name__)
            return None

    async def _wait_price(self, page: Any, nm: int, timeout_ms: int) -> Decimal | None:
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + timeout_ms / 1000
        while loop.time() < deadline:
            try:
                title = await page.title()
            except Exception:
                await asyncio.sleep(_POLL_INTERVAL)
                continue
            if _NOT_FOUND in title:
                logger.info("price: product %s not found on the catalog page", nm)
                return None
            price = parse_title_price(title)
            if price is not None:
                logger.info("price: nm=%s -> %s (title)", nm, price)
                return price
            if _is_product_title(title):
                try:
                    text = await page.inner_text("body")
                except Exception:
                    text = ""
                price = parse_body_price(text)
                if price is not None:
                    logger.info("price: nm=%s -> %s (body)", nm, price)
                    return price
            elif _is_idle_title(title) and loop.time() - started > _NOT_FOUND_AFTER:
                logger.info("price: product %s page did not open", nm)
                return None
            await asyncio.sleep(_POLL_INTERVAL)
        logger.warning("price: timeout waiting for the price of nm=%s", nm)
        return None

    async def _rotate_ip(self) -> None:
        try:
            response = await self._client.get(get_settings().PROXY_ROTATE_URL)
            logger.info("proxy IP rotated: status=%s", response.status_code)
        except httpx.HTTPError as exc:
            logger.warning("proxy rotation failed: %s", type(exc).__name__)
