"""Reviews module errors (contract: ADR-002, EN messages, no user keys)."""

from src.core.errors import SyncleError


class ReviewAnalysisError(SyncleError):
    """Review analysis could not be generated or failed validation (#30)."""


class ReviewsFetchError(SyncleError):
    """Failed to fetch reviews for a product source (#32)."""
