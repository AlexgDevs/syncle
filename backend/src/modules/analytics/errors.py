from src.core.errors import SyncleError


class CardParseError(SyncleError):
    """Failed to get or parse a product card."""


class CardNotFoundError(CardParseError):
    """Product does not exist for the given source."""


class UnsupportedMarketplaceError(CardParseError):
    """Marketplace is recognized but has no parser yet."""

    def __init__(self, marketplace: str) -> None:
        super().__init__(f"Marketplace {marketplace!r} is not supported yet.")
        self.marketplace = marketplace
