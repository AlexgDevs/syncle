"""Typed errors for the infographics module (issue #62)."""

from src.core.errors import SyncleError


class InfographicsError(SyncleError):
    """Base error for the infographics module."""


class InfographicsRenderError(InfographicsError):
    """The image pipeline failed to produce usable artwork."""
