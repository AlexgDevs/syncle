from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.settings import get_settings
from src.modules.analytics.errors import CardNotFoundError, CardParseError
from src.modules.analytics.parsers.base import CardPriceSource
from src.modules.analytics.parsers.constants import BASKET_GUESSES, NM_FROM_URL
from src.modules.analytics.schemas import CompetitorCard, Review


class WbParser:
    def __init__(
        self,
        client: httpx.AsyncClient,
        price_source: CardPriceSource | None = None,
        feedbacks_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client
        self._price_source = price_source
        self._feedbacks_client = feedbacks_client or client
        self._basket_by_vol: dict[int, int] = {}

    async def parse(self, source: str) -> CompetitorCard:
        nm = self._extract_nm(source)
        data = await self._fetch_card_json(nm)
        feedbacks = await self._fetch_feedbacks(data.get("imt_id"))
        selling = data.get("selling") or {}
        price = None
        if self._price_source is not None:
            price = await self._price_source.fetch_price(nm)
        return CompetitorCard(
            source=source.strip(),
            title=data.get("imt_name"),
            description=data.get("description"),
            brand=selling.get("brand_name"),
            category=data.get("subj_name"),
            price=price,
            rating=self._as_float(feedbacks.get("valuation")) if feedbacks else None,
            feedbacks_count=(
                self._as_int(feedbacks.get("feedbackCount")) if feedbacks else None
            ),
        )

    async def get_reviews(self, source: str) -> list[Review]:
        """Extract reviews for a WB product.

        feedbacks2.wb.ru returns a single batch per request — query-level
        pagination (``take``/``skip``/``page``) is ignored by the endpoint —
        so the configurable cap (``REVIEWS_CAP``) is applied client-side.

        Best effort: malformed entries are skipped and missing fields become
        None, so a bad entry never fails the whole batch. A network failure
        or a non-JSON response raises ``CardParseError``.
        """
        nm = self._extract_nm(source)
        data = await self._fetch_card_json(nm)
        feedbacks = await self._fetch_feedbacks(data.get("imt_id"))
        if feedbacks is None:
            raise CardParseError("Wildberries reviews service is unavailable.")
        raw = feedbacks.get("feedbacks")
        if not isinstance(raw, list):
            return []
        cap = get_settings().REVIEWS_CAP
        reviews: list[Review] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            review = self._to_review(item)
            if review is not None:
                reviews.append(review)
            if len(reviews) >= cap:
                break
        return reviews

    @classmethod
    def _to_review(cls, item: dict[str, Any]) -> Review | None:
        review_id = item.get("id")
        if not isinstance(review_id, str) or not review_id:
            return None
        details = item.get("wbUserDetails")
        author = details.get("name") if isinstance(details, dict) else None
        return Review(
            review_id=review_id,
            text=cls._as_str(item.get("text")),
            pros=cls._as_str(item.get("pros")),
            cons=cls._as_str(item.get("cons")),
            rating=cls._as_int(item.get("productValuation")),
            date=cls._as_datetime(item.get("createdDate")),
            author=author if isinstance(author, str) and author else None,
        )

    @staticmethod
    def _as_str(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _extract_nm(source: str) -> int:
        value = source.strip()
        if value.isdigit():
            return int(value)
        parsed = urlparse(value if "://" in value else f"https://{value}")
        match = NM_FROM_URL.search(parsed.path)
        if match is None:
            raise CardParseError(
                f"Wildberries article not found in the source: {value!r}"
            )
        return int(match.group(1))

    async def _fetch_card_json(self, nm: int) -> dict[str, Any]:
        vol, part = nm // 100_000, nm // 1000
        saw_response = False
        for basket in self._candidate_baskets(vol):
            url = (
                f"https://basket-{basket:02d}.wbbasket.ru"
                f"/vol{vol}/part{part}/{nm}/info/ru/card.json"
            )
            try:
                response = await self._client.get(url)
            except httpx.HTTPError:
                continue
            saw_response = True
            if response.status_code != 200:
                continue
            try:
                data = response.json()
            except ValueError:
                continue
            if not isinstance(data, dict) or not data:
                continue
            self._basket_by_vol[vol] = basket
            return data
        if not saw_response:
            raise CardParseError("Wildberries service is unavailable, try again later.")
        raise CardNotFoundError(f"Product with article {nm} was not found.")

    async def _fetch_feedbacks(self, imt_id: Any) -> dict[str, Any] | None:
        if not isinstance(imt_id, int):
            return None
        try:
            response = await self._feedbacks_client.get(
                f"https://feedbacks2.wb.ru/feedbacks/v2/{imt_id}"
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def _candidate_baskets(self, vol: int) -> list[int]:
        guess = self._basket_by_vol.get(vol) or self._guess_basket(vol)
        return [guess] + [b for b in range(1, 47) if b != guess]

    @staticmethod
    def _guess_basket(vol: int) -> int:
        for upper, basket in BASKET_GUESSES:
            if vol <= upper:
                return basket
        return 1

    @staticmethod
    def _as_float(value: Any) -> float | None:
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

    @classmethod
    def _as_int(cls, value: Any) -> int | None:
        number = cls._as_float(value)
        return int(number) if number is not None else None
