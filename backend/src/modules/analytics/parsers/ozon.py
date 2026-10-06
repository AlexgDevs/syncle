import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote, urlparse

from src.core.settings import get_settings
from src.modules.analytics.errors import CardNotFoundError, CardParseError
from src.modules.analytics.parsers.cdp import CdpJsonClient
from src.modules.analytics.parsers.constants import OZON_CATALOG_ID, OZON_PRODUCT_ID
from src.modules.analytics.schemas import CompetitorCard, Review

_PAGE_API = "https://www.ozon.ru/api/composer-api.bx/page/json/v2?url="
_REVIEWS_API = "https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2?url="

# Reviews arrive in small server-driven pages; the client-side cap
# (``REVIEWS_CAP``) stops pagination much earlier.
_MAX_REVIEW_PAGES = 50

_CHALLENGE_MARKERS = ("fab_chlg", "challengeURL", "incidentId")


class OzonParser:
    """Parses Ozon product data through a real browser session.

    Ozon answers plain HTTP clients with a JS bot challenge, so every
    request runs inside a manually started Edge (``connect_over_cdp``);
    see ``CdpJsonClient`` for the transport details.
    """

    def __init__(self, client: CdpJsonClient | None = None) -> None:
        self._client = client or CdpJsonClient(get_settings().OZON_CDP_URL)

    async def parse(self, source: str) -> CompetitorCard:
        path = self._extract_path(source)
        data = await self._fetch_page(path, source)
        states = self._widget_states(data)
        heading = self._state(states, "webProductHeading") or {}
        price_widget = self._state(states, "webPrice") or {}
        score = self._state(states, "webReviewProductScore") or {}
        return CompetitorCard(
            source=source.strip(),
            title=self._as_str(heading.get("title")),
            description=self._seo_description(data),
            brand=self._brand(self._state(states, "webBrand") or {}),
            category=self._category(self._state(states, "breadCrumbs") or {}),
            price=self._price(price_widget.get("price")),
            rating=self._as_float(score.get("totalScore")),
            feedbacks_count=self._as_int(score.get("reviewsCount")),
        )

    async def get_reviews(self, source: str) -> list[Review]:
        """Extract reviews for an Ozon product.

        The reviews list is served by the ``pdp-part`` endpoint in small
        pages (``layout_container=reviewshelfpaginator``); pagination
        stops when a page brings no entries, the reported total is
        reached, or the configurable cap (``REVIEWS_CAP``) is hit.

        Best effort: malformed entries are skipped and missing fields
        become None, so a bad entry never fails the whole batch. A
        network failure or a non-JSON response raises ``CardParseError``.
        """
        article = self._extract_article(source)
        cap = get_settings().REVIEWS_CAP
        reviews: list[Review] = []
        page = 1
        while len(reviews) < cap and page <= _MAX_REVIEW_PAGES:
            path = (
                f"/product/{article}/reviews/pdp-part"
                f"?layout_container=reviewshelfpaginator"
                f"&layout_page_index={page}&tab=reviews"
            )
            status, body = await self._client.fetch_text(
                _REVIEWS_API + quote(path, safe="")
            )
            if status == 404:
                if page == 1:
                    raise CardNotFoundError(
                        f"Ozon product was not found: {source.strip()!r}"
                    )
                break
            data = self._decode(status, body, source)
            entries, total = self._review_entries(data)
            if not entries:
                break
            for item in entries:
                if not isinstance(item, dict):
                    continue
                review = self._to_review(item)
                if review is not None:
                    reviews.append(review)
                if len(reviews) >= cap:
                    break
            if total is not None and len(reviews) >= total:
                break
            page += 1
        return reviews

    async def _fetch_page(self, path: str, source: str) -> dict[str, Any]:
        status, body = await self._client.fetch_text(_PAGE_API + quote(path, safe=""))
        return self._decode(status, body, source)

    def _decode(self, status: int, body: str, source: str) -> dict[str, Any]:
        if status == 404:
            raise CardNotFoundError(f"Ozon product was not found: {source.strip()!r}")
        if status != 200:
            if self._is_challenge(body):
                raise CardParseError(
                    "Ozon served a bot challenge instead of the page data."
                )
            raise CardParseError(f"Ozon responded with HTTP {status}.")
        try:
            data = json.loads(body)
        except ValueError as exc:
            if self._is_challenge(body):
                raise CardParseError(
                    "Ozon served a bot challenge instead of the page data."
                ) from exc
            raise CardParseError("Ozon returned a non-JSON response.") from exc
        if not isinstance(data, dict):
            raise CardParseError("Ozon returned an unexpected payload.")
        return data

    @staticmethod
    def _is_challenge(body: str) -> bool:
        return "fab_chlg" in body or ("incidentId" in body and "challengeURL" in body)

    @staticmethod
    def _widget_states(data: dict[str, Any]) -> dict[str, Any]:
        states = data.get("widgetStates")
        if not isinstance(states, dict):
            raise CardParseError("Ozon page payload has no widget states.")
        return states

    @staticmethod
    def _state(states: dict[str, Any], prefix: str) -> dict[str, Any] | None:
        for key, value in states.items():
            # Keys look like "<widget>-<id>-..."; require an exact widget
            # name so e.g. "webPrice" does not match "webPriceDecreased…".
            if key != prefix and not key.startswith(f"{prefix}-"):
                continue
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except ValueError:
                    return None
                return parsed if isinstance(parsed, dict) else None
            return value if isinstance(value, dict) else None
        return None

    @staticmethod
    def _seo_description(data: dict[str, Any]) -> str | None:
        seo = data.get("seo")
        if not isinstance(seo, dict):
            return None
        meta = seo.get("meta")
        if not isinstance(meta, list):
            return None
        for item in meta:
            if not isinstance(item, dict):
                continue
            if item.get("name") != "description":
                continue
            value = item.get("content")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _brand(widget: dict[str, Any]) -> str | None:
        content = widget.get("content")
        if not isinstance(content, dict):
            return None
        title = content.get("title")
        if not isinstance(title, dict):
            return None
        texts = title.get("text")
        if not isinstance(texts, list):
            return None
        for item in texts:
            if not isinstance(item, dict):
                continue
            value = item.get("content")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _category(widget: dict[str, Any]) -> str | None:
        crumbs = widget.get("breadcrumbs")
        if not isinstance(crumbs, list) or not crumbs:
            return None
        first = crumbs[0]
        if not isinstance(first, dict):
            return None
        value = first.get("text")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _price(value: Any) -> Decimal | None:
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

    @classmethod
    def _review_entries(cls, data: dict[str, Any]) -> tuple[list[Any], int | None]:
        states = cls._widget_states(data)
        widget = cls._state(states, "webListReviews")
        if widget is None:
            return [], None
        raw = widget.get("reviews")
        entries = raw if isinstance(raw, list) else []
        total: int | None = None
        paging = widget.get("paging")
        if isinstance(paging, dict):
            reported = paging.get("total")
            if isinstance(reported, int) and not isinstance(reported, bool):
                total = reported
        return entries, total

    @classmethod
    def _to_review(cls, item: dict[str, Any]) -> Review | None:
        review_id = item.get("uuid")
        if not isinstance(review_id, str) or not review_id:
            return None
        content = item.get("content")
        content = content if isinstance(content, dict) else {}
        author = item.get("author")
        author = author if isinstance(author, dict) else {}
        name = cls._as_str(author.get("firstName")) or cls._as_str(author.get("fio"))
        return Review(
            review_id=review_id,
            text=cls._as_str(content.get("comment")),
            pros=cls._as_str(content.get("positive")),
            cons=cls._as_str(content.get("negative")),
            rating=cls._as_int(content.get("score")),
            date=cls._as_unix_datetime(item.get("updatedAt") or item.get("createdAt")),
            author=name,
        )

    @staticmethod
    def _extract_path(source: str) -> str:
        value = source.strip()
        if value.isdigit():
            return f"/product/{value}/"
        parsed = urlparse(value if "://" in value else f"https://{value}")
        path = parsed.path or "/"
        if OZON_PRODUCT_ID.match(path) or OZON_CATALOG_ID.match(path):
            return path
        raise CardParseError(f"Ozon product link is not recognized: {value!r}")

    @staticmethod
    def _extract_article(source: str) -> str:
        value = source.strip()
        if value.isdigit():
            return value
        parsed = urlparse(value if "://" in value else f"https://{value}")
        path = parsed.path or "/"
        match = OZON_PRODUCT_ID.match(path) or OZON_CATALOG_ID.match(path)
        if match is None:
            raise CardParseError(f"Ozon article not found in the source: {value!r}")
        return match.group(1)

    @staticmethod
    def _as_str(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _as_unix_datetime(value: Any) -> datetime | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if value <= 0:
            return None
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except OverflowError, OSError, ValueError:
            return None

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
