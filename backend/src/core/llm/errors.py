from src.core.errors import SyncleError


class LLMError(SyncleError):
    """Base class for LLM provider failures."""


class LLMTimeoutError(LLMError):
    """LLM request did not finish in time."""


class LLMRateLimitError(LLMError):
    """LLM provider rate limit was hit."""


class LLMUnavailableError(LLMError):
    """LLM provider is unreachable or returned an unusable response."""
