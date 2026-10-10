"""Typed LLM failures shared by the provider adapters (issues #11, #62)."""

from typing import NoReturn

from openai import (
    APIError,
    APITimeoutError,
    APIStatusError,
    RateLimitError,
)

from src.core.errors import SyncleError


class LLMError(SyncleError):
    """Base class for LLM provider failures."""


class LLMTimeoutError(LLMError):
    """LLM request did not finish in time."""


class LLMRateLimitError(LLMError):
    """LLM provider rate limit was hit."""


class LLMUnavailableError(LLMError):
    """LLM provider is unreachable or returned an unusable response."""


def raise_image_error(exc: Exception, model: str) -> NoReturn:
    """Translate openai SDK failures into typed LLM errors."""
    if isinstance(exc, APITimeoutError):
        raise LLMTimeoutError(
            f"LLM image request timed out for model {model!r}."
        ) from exc
    if isinstance(exc, RateLimitError):
        raise LLMRateLimitError(
            f"LLM image rate limit hit for model {model!r}."
        ) from exc
    if isinstance(exc, APIStatusError):
        raise LLMUnavailableError(
            f"LLM image request failed: HTTP {exc.status_code} "
            f"for model {model!r}: {exc.message}."
        ) from exc
    if isinstance(exc, APIError):
        raise LLMUnavailableError(
            f"LLM image request failed: {type(exc).__name__}."
        ) from exc
    raise exc
