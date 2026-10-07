"""Base exception hierarchy for all domain errors.

Contract (ADR-002): errors carry EN messages and no user-facing keys.
Each adapter translates them at its own boundary:
- bot adapter: type -> RU text (describe_error);
- future API adapter: type -> JSON problem response.
Any SyncleError not mapped by an adapter falls back to its generic message.
"""


class SyncleError(Exception):
    """Base class for all project domain errors."""
