"""Normalization of user-provided product sources (URL or article)."""

from urllib.parse import ParseResult, urlparse


def parse_source(value: str) -> tuple[str, ParseResult | None]:
    """Split a source into ``(stripped, parsed URL)``.

    Digit-only sources are marketplace articles and carry no URL
    (``parsed`` is None); bare hosts are normalized with ``https://``.
    """
    stripped = value.strip()
    if stripped.isdigit():
        return stripped, None
    return stripped, urlparse(stripped if "://" in stripped else f"https://{stripped}")
