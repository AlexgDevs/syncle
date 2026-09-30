from typing import Any
from urllib.parse import urlparse

import httpx

from src.modules.analytics.errors import CardNotFoundError, CardParseError
from src.modules.analytics.parsers.base import CardPriceSource
from src.modules.analytics.parsers.constants import BASKET_GUESSES, NM_FROM_URL
from src.modules.analytics.schemas import CompetitorCard


class WbParser:
    def __init__(
        self,
        client: httpx.AsyncClient,
        price_source: CardPriceSource | None = None,
    ) -> None:
        self._client = client
        self._price_source = price_source
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
            response = await self._client.get(
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
