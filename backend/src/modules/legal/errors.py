"""Typed failures for the legal module (issues #53-#59, ADR-002)."""

from src.core.errors import SyncleError


class LegalScanError(SyncleError):
    """A legal scan could not be completed."""


class LegalDocumentError(SyncleError):
    """A seller document could not be ingested or reviewed."""
