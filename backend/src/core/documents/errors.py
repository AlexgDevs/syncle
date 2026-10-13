"""Typed document parsing failures (core port, issue #15)."""

from src.core.errors import SyncleError


class DocumentParseError(SyncleError):
    """The uploaded file could not be parsed into text."""


class UnsupportedDocumentError(DocumentParseError):
    """The file format is not one of the supported document types."""
