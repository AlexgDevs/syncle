import asyncio
from typing import Any

from playwright.async_api import Browser, Page, Playwright, async_playwright

from src.modules.analytics.errors import OzonBrowserError
from src.modules.analytics.parsers.constants import OZON_ORIGIN

_FETCH_JS = """
async (url) => {
    const response = await fetch(url, { credentials: "include" });
    return { status: response.status, body: await response.text() };
}
"""

_NAVIGATE_TIMEOUT_MS = 30_000


class CdpJsonClient:
    """Fetches remote JSON through a real browser session over CDP.

    Ozon rejects plain HTTP clients with a JS bot challenge, so requests
    execute inside a manually started Edge that exposes a debugging
    endpoint (``connect_over_cdp`` does not inject automation flags).

    One shared page per origin serializes requests under a lock; the
    browser keeps its own cookies and challenge tokens fresh.
    """

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def fetch_text(self, url: str) -> tuple[int, str]:
        """Returns ``(status, body)`` for a GET executed inside the browser."""
        async with self._lock:
            try:
                page = await self._page()
                payload: dict[str, Any] = await page.evaluate(_FETCH_JS, url)
            except OzonBrowserError:
                raise
            except Exception as exc:
                await self._teardown()
                raise OzonBrowserError(
                    "Ozon browser session failed while fetching data."
                ) from exc
        status = payload.get("status")
        body = payload.get("body")
        if not isinstance(status, int) or not isinstance(body, str):
            raise OzonBrowserError("Ozon browser session returned an invalid response.")
        return status, body

    async def _page(self) -> Page:
        browser = await self._browser_or_connect()
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            context = await browser.new_context()
        for page in context.pages:
            if page.url.startswith(OZON_ORIGIN):
                return page
        page = await context.new_page()
        try:
            await page.goto(
                f"{OZON_ORIGIN}/",
                wait_until="domcontentloaded",
                timeout=_NAVIGATE_TIMEOUT_MS,
            )
        except Exception:
            if not page.url.startswith(OZON_ORIGIN):
                await page.close()
                raise OzonBrowserError(
                    "Ozon browser session could not open an Ozon page."
                )
        return page

    async def _browser_or_connect(self) -> Browser:
        if self._browser is not None:
            return self._browser
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._endpoint
            )
        except Exception as exc:
            await self._teardown()
            raise OzonBrowserError(
                "Ozon browser session is unavailable: cannot connect to "
                f"the CDP endpoint {self._endpoint!r}."
            ) from exc
        return self._browser

    async def _teardown(self) -> None:
        playwright, self._playwright = self._playwright, None
        self._browser = None
        if playwright is None:
            return
        try:
            await playwright.stop()
        except Exception:
            pass
