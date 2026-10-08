"""Content module errors (contract: ADR-002, EN messages, no user keys)."""

from src.core.errors import SyncleError


class SeoGenerationError(SyncleError):
    """SEO text could not be generated or failed output validation (#25)."""
