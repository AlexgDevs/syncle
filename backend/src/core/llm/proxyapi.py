from functools import lru_cache

from openai import (
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from src.core.llm.errors import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from src.core.llm.provider import LLMProvider
from src.core.settings import get_settings


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
    ) -> str:
        messages: list[ChatCompletionMessageParam] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
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
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LLMUnavailableError(
                f"LLM returned an empty completion for model {self._model!r}."
            )
        return content


@lru_cache
def get_llm_provider() -> LLMProvider | None:
    """Return the shared provider, or None when LLM is not configured.

    Cached: the AsyncOpenAI client is created at most once per process.
    TODO(G01): image-generation entry point once infographics unfreeze.
    """
    cfg = get_settings()
    if not cfg.LLM_API_KEY or not cfg.LLM_MODEL:
        return None
    client = AsyncOpenAI(
        api_key=cfg.LLM_API_KEY,
        base_url=cfg.LLM_BASE_URL,
        timeout=cfg.LLM_TIMEOUT,
        max_retries=2,
    )
    return ProxyApiProvider(client=client, model=cfg.LLM_MODEL)
