from urllib.parse import urlparse


def is_valid_card_input(value: str) -> bool:
    if value.isdigit():
        return True
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)
