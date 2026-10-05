"""Shared outbound HTTP layer (#17).

One factory, one cached client per host profile:

- ``basket``    — Wildberries basket hosts (card.json);
- ``feedbacks`` — feedbacks2.wb.ru;
- ``ozon``      — Ozon (routes through PROXY_URL when configured);
- LLM gateway   — :func:`get_llm_client`; the OpenAI SDK speaks ``httpx2``
  (its own httpx fork), so it gets a dedicated plain client and does its own
  retry with backoff (``max_retries`` in proxyapi.py).

Each httpx client owns a connection pool, a per-profile timeout and retries
with exponential backoff on timeouts and 5xx responses (see RetryTransport).
"""

import asyncio
import logging
from functools import lru_cache

import httpx
import httpx2

from src.core.settings import get_settings

logger = logging.getLogger(__name__)

_MAX_BACKOFF = 4.0  # seconds

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

_PROFILES = frozenset({"basket", "feedbacks", "ozon"})


class RetryTransport(httpx.AsyncBaseTransport):
    """Transport wrapper: exponential backoff on timeouts and 5xx.

    Rebuilds the request per attempt from the already-read body, so GET/JSON
    requests are replayed safely; non-idempotent streaming bodies are out of
    scope for this layer.
    """

    def __init__(
        self,
        *,
        attempts: int,
        backoff: float,
        proxy: str | None = None,
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._attempts = max(1, attempts)
        self._backoff = backoff
        self._inner = (
            inner if inner is not None else httpx.AsyncHTTPTransport(proxy=proxy)
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        content = await request.aread()
        failure: httpx.TimeoutException | None = None
        for attempt in range(self._attempts):
            if attempt:
                delay = min(self._backoff * (2 ** (attempt - 1)), _MAX_BACKOFF)
                await asyncio.sleep(delay)
            candidate = httpx.Request(
                request.method, request.url, headers=request.headers, content=content
            )
            try:
                response = await self._inner.handle_async_request(candidate)
            except httpx.TimeoutException as exc:
                failure = exc
                logger.debug(
                    "http retry %s %s (attempt %s/%s): %s",
                    request.method,
                    request.url.host,
                    attempt + 1,
                    self._attempts,
                    type(exc).__name__,
                )
                continue
            if response.status_code >= 500 and attempt < self._attempts - 1:
                logger.debug(
                    "http retry %s %s (attempt %s/%s): status %s",
                    request.method,
                    request.url.host,
                    attempt + 1,
                    self._attempts,
                    response.status_code,
                )
                await response.aclose()
                continue
            return response
        assert failure is not None
        raise failure

    async def aclose(self) -> None:
        await self._inner.aclose()


@lru_cache
def get_client(profile: str) -> httpx.AsyncClient:
    """Return the shared client for a host profile (at most once per process)."""
    if profile not in _PROFILES:
        raise ValueError(f"Unknown HTTP profile: {profile!r}")
    cfg = get_settings()
    proxy = (cfg.PROXY_URL or None) if profile == "ozon" else None
    return httpx.AsyncClient(
        transport=RetryTransport(
            attempts=cfg.HTTP_MAX_RETRIES + 1,
            backoff=cfg.HTTP_BACKOFF_BASE,
            proxy=proxy,
        ),
        timeout=httpx.Timeout(cfg.HTTP_TIMEOUT),
        follow_redirects=True,
        headers=_BROWSER_HEADERS,
    )


@lru_cache
def get_llm_client() -> httpx2.AsyncClient:
    """Shared client for the OpenAI-compatible gateway (``httpx2``-based).

    Retries are left to the OpenAI SDK (``max_retries``) so backoff is not
    applied twice.
    """
    cfg = get_settings()
    return httpx2.AsyncClient(timeout=httpx2.Timeout(cfg.LLM_TIMEOUT))
