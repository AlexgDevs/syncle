"""Value coercion helpers shared by the marketplace parsers.

Marketplace payloads are loosely typed (numbers arrive as strings, bools
leak into int checks, prices carry UI decorations), so every parser had
its own copy of the same guards. This module is their single home.
"""

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    return int(number) if number is not None else None


def as_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def as_unix_datetime(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except OverflowError, OSError, ValueError:
        return None


def parse_price(value: Any) -> Decimal | None:
    """Positive price from decorated display text (``"1 234 ₽"`` → 1234)."""
    if not isinstance(value, str):
        return None
    digits = re.sub(r"[^\d,.]", "", value).replace(",", ".")
    if not digits:
        return None
    try:
        price = Decimal(digits)
    except InvalidOperation:
        return None
    return price if price > 0 else None
