import base64
import logging
from functools import lru_cache
from typing import Any, cast

from openai.types import ImagesResponse

from openai import (
    APIError,
    APITimeoutError,
    APIStatusError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import (
    ChatCompletionContentPartParam,
    ChatCompletionMessageParam,
)

from src.core.http import get_llm_client
from src.core.llm.errors import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    raise_image_error,
)
from src.core.llm.provider import ImageProvider, LLMProvider
from src.core.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _image_part(image: bytes) -> ChatCompletionContentPartParam:
    encoded = base64.b64encode(image).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
    }


class ProxyApiProvider:
    """LLMProvider adapter over an OpenAI-compatible gateway (ProxyAPI)."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        images: list[bytes] | None = None,
    ) -> str:
        messages: list[ChatCompletionMessageParam] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        if images:
            parts: list[ChatCompletionContentPartParam] = [
                {"type": "text", "text": prompt}
            ]
            parts.extend(_image_part(image) for image in images)
            messages.append({"role": "user", "content": parts})
        else:
            messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APITimeoutError as exc:
            raise LLMTimeoutError(
                f"LLM request timed out for model {self._model!r}."
            ) from exc
        except RateLimitError as exc:
            raise LLMRateLimitError(
                f"LLM rate limit hit for model {self._model!r}."
            ) from exc
        except APIError as exc:
            raise LLMUnavailableError(
                f"LLM request failed: {type(exc).__name__}."
            ) from exc
        self._log_usage(response)
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LLMUnavailableError(
                f"LLM returned an empty completion for model {self._model!r}."
            )
        return content

    def _log_usage(self, response: object) -> None:
        """Log token usage per call for cost control (#11); never logs the key."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        logger.info(
            "llm usage: model=%s prompt=%s completion=%s total=%s",
            self._model,
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            getattr(usage, "total_tokens", "?"),
        )


def _build_client(
    cfg: Settings, *, timeout: float | None = None, base_url: str | None = None
) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=cfg.LLM_API_KEY,
        base_url=base_url or cfg.LLM_BASE_URL,
        timeout=timeout or cfg.LLM_TIMEOUT,
        max_retries=2,
        http_client=get_llm_client(),
    )


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    """Return the shared provider, or None when LLM is not configured.

    Cached: the AsyncOpenAI client is created at most once per process.
    """
    cfg = get_settings()
    if not cfg.LLM_API_KEY or not cfg.LLM_MODEL:
        return None
    return ProxyApiProvider(client=_build_client(cfg), model=cfg.LLM_MODEL)


@lru_cache
def get_vision_provider() -> LLMProvider | None:
    """Return the vision provider for photo input (#27), or None.

    Uses LLM_VISION_MODEL, falling back to LLM_MODEL; None when neither
    is configured (the bot then degrades to text-only SEO generation).
    """
    cfg = get_settings()
    model = cfg.LLM_VISION_MODEL or cfg.LLM_MODEL
    if not cfg.LLM_API_KEY or not model:
        return None
    return ProxyApiProvider(client=_build_client(cfg), model=model)


class ProxyApiImageProvider:
    """ImageProvider over OpenAI-compatible /images/generations|edits.

    Input photos (infographics #62) go through the multipart edits
    endpoint so real products are composited; quality/input_fidelity
    are optional knobs — models that reject them get one bare retry.
    """

    def __init__(self, client: AsyncOpenAI, model: str, quality: str = "") -> None:
        self._client = client
        self._model = model
        self._quality = quality

    async def generate_image(
        self,
        prompt: str,
        *,
        size: str,
        images: list[bytes] | None = None,
    ) -> bytes:
        opts: dict[str, str] = {}
        if self._quality:
            opts["quality"] = self._quality
        if images:
            opts["input_fidelity"] = "high"  # keep the product recognizable
        try:
            response = await self._request(prompt, size, images, opts)
        except APIStatusError as exc:
            if exc.status_code != 400 or not opts:
                raise_image_error(exc, self._model)
            logger.warning(
                "image request rejected optional params (%s); retrying bare",
                exc.message,
            )
            try:
                response = await self._request(prompt, size, images, {})
            except (APITimeoutError, RateLimitError, APIStatusError, APIError) as retry:
                raise_image_error(retry, self._model)
        item = response.data[0] if response.data else None
        encoded = item.b64_json if item is not None else None
        if not encoded:
            raise LLMUnavailableError(
                f"LLM returned no image data for model {self._model!r}."
            )
        data = base64.b64decode(encoded)
        logger.info(
            "llm image: model=%s size=%s inputs=%d bytes=%d",
            self._model,
            size,
            len(images or []),
            len(data),
        )
        return data

    async def _request(
        self,
        prompt: str,
        size: str,
        images: list[bytes] | None,
        opts: dict[str, str],
    ) -> ImagesResponse:
        kwargs: dict[str, Any] = {"model": self._model, "prompt": prompt, "size": size}
        kwargs.update(opts)
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


@lru_cache
def get_image_provider() -> ImageProvider | None:
    """Return the image generation provider (#62), or None.

    AITunnel (Gemini image models, RUB billing) owns image generation when
    AITUNNEL_API_KEY is set; otherwise LLM_IMAGE_MODEL routes through this
    gateway as a manual fallback — text models cannot draw, so an empty
    model keeps image generation unavailable. Image calls get a longer
    timeout than text completions. The quality knob applies to the
    gpt-image family only: other models reject it (one bare retry is
    wasted on each call otherwise).
    """
    from src.core.llm.aitunnel import get_aitunnel_provider

    aitunnel = get_aitunnel_provider()
    if aitunnel is not None:
        return aitunnel
    cfg = get_settings()
    if not cfg.LLM_API_KEY or not cfg.LLM_IMAGE_MODEL:
        return None
    quality = ""
    leaf = cfg.LLM_IMAGE_MODEL.rsplit("/", 1)[-1]
    if leaf.startswith("gpt-image"):
        quality = cfg.LLM_IMAGE_QUALITY
    return ProxyApiImageProvider(
        client=_build_client(
            cfg,
            timeout=max(cfg.LLM_TIMEOUT, 120.0),
            base_url=cfg.LLM_IMAGE_BASE_URL or None,
        ),
        model=cfg.LLM_IMAGE_MODEL,
        quality=quality,
    )
