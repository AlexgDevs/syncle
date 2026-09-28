from decimal import Decimal

from pydantic import BaseModel


class CompetitorCard(BaseModel):
    source: str
    title: str | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    price: Decimal | None = None
    rating: float | None = None
    feedbacks_count: int | None = None


class AnalysisReport(BaseModel):
    competitor: CompetitorCard
    own_card: CompetitorCard | None = None
    missed_seo_keys: list[str] = []
    content_weaknesses: list[str] = []
    optimal_price: Decimal | None = None
