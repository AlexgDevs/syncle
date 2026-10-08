import base64
import logging
from functools import lru_cache

from openai import (
    APIError,
    APITimeoutError,
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
)
from src.core.llm.provider import LLMProvider
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


def _build_client(cfg: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=cfg.LLM_API_KEY,
        base_url=cfg.LLM_BASE_URL,
        timeout=cfg.LLM_TIMEOUT,
        max_retries=2,
        http_client=get_llm_client(),
    )


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    """Return the shared provider, or None when LLM is not configured.

    Cached: the AsyncOpenAI client is created at most once per process.
    TODO(G01): image-generation entry point once infographics unfreeze.
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
