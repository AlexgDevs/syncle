"""Finance domain schemas (issues #45, #49, #51).

Money values are ``Decimal`` in RUB; percentages are ``Decimal`` in
percentage points (45.5 means 45.5%). No aiogram imports — the bot
adapter renders these structures on its own side of the boundary.
"""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.modules.analytics.enums import Marketplace


class FeeKind(StrEnum):
    """Classification of a suspicious settlement-report charge (#51)."""

    FINE = "fine"
    HIDDEN_FEE = "hidden_fee"
    COMMISSION_OVER = "commission_over"
    LOGISTICS_HIGH = "logistics_high"
    STORAGE_HIGH = "storage_high"


class UnitInputs(BaseModel):
    """Manual unit-economics inputs (scene A, #47/#48).

    ``unit_expenses`` is the seller's per-unit expense lump (commission,
    logistics, storage, marketing — whatever the seller knows).
    """

    model_config = ConfigDict(extra="ignore")

    price: Decimal
    unit_cost: Decimal
    unit_expenses: Decimal
    quantity: Decimal


class ProfitabilityReport(BaseModel):
    """Profit & loss for a batch of units (#45).

    ``net_profit = revenue - cogs - commission - logistics - storage -
    marketing - fines - other_expenses``. ``margin_pct`` is relative to
    revenue (0 when revenue is 0). ``break_even_price`` is the per-unit
    price at which ``net_profit`` equals 0; ``None`` when the input does
    not define one (e.g. totals computed from a settlement report).
    """

    model_config = ConfigDict(extra="ignore")

    revenue: Decimal
    cogs: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    logistics: Decimal = Decimal("0")
    storage: Decimal = Decimal("0")
    marketing: Decimal = Decimal("0")
    fines: Decimal = Decimal("0")
    other_expenses: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    margin_pct: Decimal = Decimal("0")
    break_even_price: Decimal | None = None


class CostBreakdown(BaseModel):
    """Tariff-estimated deductions for a batch (#46/#47).

    Estimated from the reference tariff tables; the authoritative per-SKU
    rates live in the seller cabinet.
    """

    model_config = ConfigDict(extra="ignore")

    commission: Decimal
    logistics: Decimal
    storage: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.logistics + self.storage


class SettlementRow(BaseModel):
    """One mapped row of a settlement report (#49/#50).

    Deduction columns (returns, commissions, logistics, storage, fines)
    are normalized to positive magnitudes; ``sales`` keeps its sign and
    ``adjustments`` stays signed (positive = money back to the seller).
    ``unknown`` keeps numeric cells whose headers were not recognized —
    the detector inspects them for hidden fees (#51).
    """

    model_config = ConfigDict(extra="ignore")

    row_number: int
    period: str = ""
    sales: Decimal = Decimal("0")
    returns: Decimal = Decimal("0")
    commissions: Decimal = Decimal("0")
    logistics: Decimal = Decimal("0")
    storage: Decimal = Decimal("0")
    fines: Decimal = Decimal("0")
    adjustments: Decimal = Decimal("0")
    unknown: dict[str, Decimal] = Field(default_factory=dict)


class FeeFinding(BaseModel):
    """Suspicious charge highlighted by the detector (#51).

    ``source_row`` is the 1-based row reference in the source table
    (0 = report-wide finding); ``detail`` is a short RU explanation —
    user-facing content, same exception as the legal catalog.
    """

    model_config = ConfigDict(extra="ignore")

    kind: FeeKind
    amount: Decimal
    source_row: int = 0
    detail: str = ""


class ReportAnalysis(BaseModel):
    """Settlement report analysis result (#49-#51, delivered by #52)."""

    model_config = ConfigDict(extra="ignore")

    filename: str
    marketplace: Marketplace | None = None
    row_count: int = 0
    totals: ProfitabilityReport
    findings: list[FeeFinding] = Field(default_factory=list)
    effective_commission_pct: Decimal | None = None
    tariffs_as_of: str = ""


class FinanceReportPayload(BaseModel):
    """Light job payload for the settlement report analysis (#52).

    The report file travels through the Redis stash; the payload stays
    JSON-light for taskiq.
    """

    model_config = ConfigDict(extra="ignore")

    chat_id: int
    status_message_id: int
    filename: str
