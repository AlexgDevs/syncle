"""Typed failures for the finance module (issues #45-#52, ADR-002)."""

from src.core.errors import SyncleError


class FinanceError(SyncleError):
    """A finance calculation or analysis could not be completed."""


class ReportParseError(FinanceError):
    """An uploaded settlement report could not be parsed or mapped."""
