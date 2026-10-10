"""AITunnel image gateway adapter (infographics #62, pipeline v4).

AITunnel (https://aitunnel.ru) is an OpenAI-compatible reseller with RUB
billing, so the standard AsyncOpenAI client works with base_url
``https://api.aitunnel.ru/v1``. Product photos go through the multipart
``/images/edits`` endpoint (Gemini image models accept up to 16 inputs,
prompt up to 32k chars), text-only posters through ``/images/generations``.

Responses carry the picture either as ``b64_json`` or as ``data:`` URL in
``url`` — both are decoded here; a plain http(s) URL is downloaded once.
"""

import base64
import logging
from functools import lru_cache
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types import ImagesResponse

from src.core.http import get_llm_client
from src.core.llm.errors import LLMUnavailableError, raise_image_error
from src.core.llm.provider import ImageProvider
from src.core.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_DATA_URL_PREFIX = "data:image/"


class AitunnelImageProvider:
    """ImageProvider over AITunnel's OpenAI-compatible images API."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def generate_image(
        self,
        prompt: str,
        *,
        size: str,
        images: list[bytes] | None = None,
    ) -> bytes:
        try:
            response = await self._request(prompt, size, images)
        except Exception as exc:  # noqa: BLE001 — typed below
            raise_image_error(exc, self._model)
        item = response.data[0] if response.data else None
        if item is None:
            raise LLMUnavailableError(
                f"LLM returned no image data for model {self._model!r}."
            )
        data = await self._decode_item(item)
        logger.info(
            "llm image: model=%s size=%s inputs=%d bytes=%d usage=%s",
            self._model,
            size,
            len(images or []),
            len(data),
            _usage_summary(response),
        )
        return data

    async def _decode_item(self, item: Any) -> bytes:
        """Extract raw image bytes from one response item."""
        encoded = getattr(item, "b64_json", None)
        if encoded:
            return base64.b64decode(encoded)
        url = getattr(item, "url", None)
        if not url:
            raise LLMUnavailableError(
                f"LLM returned no image data for model {self._model!r}."
            )
        if str(url).startswith(_DATA_URL_PREFIX):
            payload = str(url).split(",", 1)[-1]
            return base64.b64decode(payload)
        return await self._download(str(url))

    async def _download(self, url: str) -> bytes:
        """Fetch a remote image URL (AITunnel normally returns data: URLs)."""
        try:
            response = await get_llm_client().get(url)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — httpx2 errors vary by failure
            raise LLMUnavailableError(
                f"LLM image download failed for model {self._model!r}: "
                f"{type(exc).__name__}."
            ) from exc
        return response.content

    async def _request(
        self,
        prompt: str,
        size: str,
        images: list[bytes] | None,
    ) -> ImagesResponse:
        kwargs: dict[str, Any] = {"model": self._model, "prompt": prompt, "size": size}
        if images:
            sources = [
                (f"photo{index}.png", data) for index, data in enumerate(images, 1)
            ]
            kwargs["image"] = sources if len(sources) > 1 else sources[0]
            response = await self._client.images.edit(**kwargs)
        else:
            kwargs["n"] = 1
            response = await self._client.images.generate(**kwargs)
        # **kwargs untyped: both overloads resolve to ImagesResponse here
        return cast(ImagesResponse, response)


def _usage_summary(response: ImagesResponse) -> str:
    """Compact usage report for cost tracking; "-" when absent."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return "-"
    return ",".join(
        f"{key}={getattr(usage, key, '?')}"
        for key in ("total_tokens", "input_tokens", "output_tokens")
        if getattr(usage, key, None) is not None
    )


@lru_cache
def get_aitunnel_provider() -> ImageProvider | None:
    """Shared AITunnel image provider, or None when AITUNNEL_API_KEY is unset.

    Image calls get a longer timeout than text completions; the client is
    created at most once per process.
    """
    cfg: Settings = get_settings()
    if not cfg.AITUNNEL_API_KEY or not cfg.AITUNNEL_IMAGE_MODEL:
        return None
    return AitunnelImageProvider(
        client=AsyncOpenAI(
            api_key=cfg.AITUNNEL_API_KEY,
            base_url=cfg.AITUNNEL_IMAGE_BASE_URL,
            timeout=max(cfg.LLM_TIMEOUT, 120.0),
            max_retries=2,
            http_client=get_llm_client(),
        ),
        model=cfg.AITUNNEL_IMAGE_MODEL,
    )
