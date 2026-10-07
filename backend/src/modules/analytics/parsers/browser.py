"""Shared Playwright session for Wildberries scraping (ADR-004).

Wildberries serves an anti-bot challenge to plain HTTP clients, so both
the niche search and the price source drive a real Chromium. Every run
gets a fresh profile with an identical anti-detect setup — the launch
config comes from the shared browser scraping settings.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from src.core.settings import get_settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)
HIDE_WEBDRIVER = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
)


class BrowserUnavailable(RuntimeError):
    """Playwright is not installed or cannot start."""


@asynccontextmanager
async def wb_browser_session() -> AsyncIterator[Any]:
    """Launch Chromium with the shared anti-detect setup; yield a new page."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise BrowserUnavailable(
            "Playwright is not installed; browser scraping is unavailable."
        ) from exc
    cfg = get_settings()
    launch_kwargs: dict[str, Any] = {"headless": cfg.PRICE_HEADLESS}
    if cfg.PROXY_URL:
        launch_kwargs["proxy"] = {"server": cfg.PROXY_URL}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**launch_kwargs)
        try:
            context = await browser.new_context(
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                user_agent=USER_AGENT,
                viewport={"width": 1440, "height": 1000},
            )
            await context.add_init_script(HIDE_WEBDRIVER)
            yield await context.new_page()
        finally:
            await browser.close()
