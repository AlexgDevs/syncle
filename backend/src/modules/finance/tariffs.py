"""Reference tariff tables for Wildberries and Ozon (issue #46).

Public rates collected from marketplace announcements and seller
analytical sources, frozen "as of" :data:`TARIFFS_AS_OF`. Every value is
a range, never a point estimate: the authoritative rate for a SKU lives
in the seller cabinet and changes with category, scheme, promo programs
and warehouse coefficients.

Used by the calculator (#47) for commission-aware scenarios and by the
detector (#51) to reconcile settlement-report charges against the
published norms.

Column-name keywords and fee titles are RU because they are user-facing
reference content (same exception as the legal risk catalog).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.modules.analytics.enums import Marketplace

TARIFFS_AS_OF = date(2026, 10, 1)

# Effective commission above range max + this slack is flagged (#51)
COMMISSION_TOLERANCE_PP = Decimal("5")


@dataclass(frozen=True)
class CommissionRange:
    """Published commission range in percentage points."""

    min_pct: Decimal
    max_pct: Decimal
    note: str = ""


@dataclass(frozen=True)
class PriceSegment:
    """Ozon price segment: applies when price <= ``max_price`` (None = open)."""

    max_price: Decimal | None
    commission: CommissionRange


@dataclass(frozen=True)
class ShareThresholds:
    """Detection thresholds: share of sales above which a line looks off (#51)."""

    max_logistics_share_pct: Decimal
    max_storage_share_pct: Decimal


@dataclass(frozen=True)
class FeeReference:
    """Known hidden fee or typical fine encoded as a reference entry (#46).

    ``keywords`` match settlement-report column headers (lowercased
    substring match); ``description`` is rendered to the user as-is.
    """

    fee_id: str
    marketplace: Marketplace | None  # None = applies to both
    keywords: tuple[str, ...]
    description: str
    typical_amount: Decimal | None = None  # per unit, when the fee is fixed


# --- Wildberries (rates as of 2026-10-01; +5/+6/+20 pp raise of 2026-07-07) ---

WB_COMMISSION = CommissionRange(
    min_pct=Decimal("5"),
    max_pct=Decimal("40"),
    note="category range after the 2026-07-07 raise (FBO +5 pp, FBS +6 pp, DBS +20 pp)",
)

WB_THRESHOLDS = ShareThresholds(
    max_logistics_share_pct=Decimal("15"),
    max_storage_share_pct=Decimal("3"),
)

# --- Ozon (rates as of 2026-10-01; segments of 2026-04-06, raise of 2026-08-28) ---

OZON_SEGMENTS: tuple[PriceSegment, ...] = (
    PriceSegment(
        max_price=Decimal("100"),
        commission=CommissionRange(
            min_pct=Decimal("17"),
            max_pct=Decimal("20"),
            note="fixed low-price segment; 14% before the 2026-08-28 raise",
        ),
    ),
    PriceSegment(
        max_price=Decimal("300"),
        commission=CommissionRange(
            min_pct=Decimal("23"),
            max_pct=Decimal("26"),
            note="fixed low-price segment; 20% before the 2026-08-28 raise",
        ),
    ),
    PriceSegment(
        max_price=None,
        commission=CommissionRange(
            min_pct=Decimal("20"),
            max_pct=Decimal("55"),
            note="category base rate for goods over 300 RUB (e.g. clothing ~50-55%, electronics ~42-44%)",
        ),
    ),
)

OZON_THRESHOLDS = ShareThresholds(
    max_logistics_share_pct=Decimal("15"),
    max_storage_share_pct=Decimal("5"),
)

# Detection fallback when the marketplace cannot be identified (#51)
GENERIC_COMMISSION = CommissionRange(
    min_pct=Decimal("4"),
    max_pct=Decimal("55"),
    note="cross-marketplace envelope",
)

GENERIC_THRESHOLDS = ShareThresholds(
    max_logistics_share_pct=Decimal("15"),
    max_storage_share_pct=Decimal("5"),
)

# --- Known hidden fees (#46) ---

HIDDEN_FEES: tuple[FeeReference, ...] = (
    FeeReference(
        fee_id="nonlocal_surcharge",
        marketplace=None,
        keywords=("нелокальн", "дальнобой", "за предел"),
        description="Нелокальная наценка: WB берёт до 2,5% от цены за доставку в другие регионы.",
    ),
    FeeReference(
        fee_id="redistribution",
        marketplace=Marketplace.WB,
        keywords=("перераспредел",),
        description="Перераспределение остатков между складами WB: 0,5–3% от цены.",
    ),
    FeeReference(
        fee_id="reverse_logistics",
        marketplace=None,
        keywords=("обратн",),
        description="Обратная логистика: возврат отправления от покупателя к продавцу.",
    ),
    FeeReference(
        fee_id="return_processing",
        marketplace=None,
        keywords=("обработка возврата", "возврат товара"),
        description="Обработка возврата: списание за приёмку возвращённого товара.",
    ),
    FeeReference(
        fee_id="acquiring",
        marketplace=None,
        keywords=("эквайр", "приём платеж", "прием платеж"),
        description="Эквайринг: комиссия за приём платежа (0,6–1,5% от суммы заказа).",
    ),
    FeeReference(
        fee_id="handling",
        marketplace=None,
        keywords=("обработка отправл", "сборка", "приёмк", "приемк"),
        description="Обработка/приёмка отправления: плата за сборку и сдачу на склад.",
    ),
    FeeReference(
        fee_id="packaging",
        marketplace=None,
        keywords=("упаков", "киз", "маркиров"),
        description="Упаковка и маркировка: доп. списание за упаковочный материал или КИЗ.",
    ),
    FeeReference(
        fee_id="regional_surcharge",
        marketplace=None,
        keywords=("за регион", "в другие регионы", "наценка за доставку"),
        description="Региональная наценка на доставку (Ozon отменял её с 2026-07-09).",
    ),
)

# --- Typical fines (#46) ---

TYPICAL_FINES: tuple[FeeReference, ...] = (
    FeeReference(
        fee_id="packaging_fine",
        marketplace=Marketplace.WB,
        keywords=("упаков", "киз", "маркиров"),
        description="Штраф WB за нарушение упаковки/маркировки: до 40 ₽ за единицу.",
        typical_amount=Decimal("40"),
    ),
    FeeReference(
        fee_id="late_shipment_fine",
        marketplace=Marketplace.WB,
        keywords=("отгруз", "просроч", "срок отгруз"),
        description="Штраф WB за просроченную отгрузку FBS (с 2026-08-31 — расчёт по часам).",
    ),
    FeeReference(
        fee_id="logistics_fine",
        marketplace=None,
        keywords=("штраф за логист", "штраф логист"),
        description="Штраф за нарушение логистических условий маркетплейса.",
    ),
    FeeReference(
        fee_id="utilization_fine",
        marketplace=None,
        keywords=("утилиз", "списание товара"),
        description="Утилизация/списание товара: плата за вынужденную утилизацию остатков.",
    ),
    FeeReference(
        fee_id="quality_fine",
        marketplace=None,
        keywords=("штраф за брак", "качеств", "поврежд"),
        description="Штраф за брак или повреждение товара при обработке.",
    ),
)


def commission_range(
    marketplace: Marketplace | None, price: Decimal | None = None
) -> CommissionRange:
    """Commission range for the marketplace and price segment (#46/#47).

    Ozon resolves by price segment; without a price or marketplace the
    generic cross-marketplace envelope is returned.
    """
    if marketplace == Marketplace.OZON:
        if price is None:
            return OZON_SEGMENTS[-1].commission
        for segment in OZON_SEGMENTS:
            if segment.max_price is None or price <= segment.max_price:
                return segment.commission
    if marketplace == Marketplace.WB:
        return WB_COMMISSION
    return GENERIC_COMMISSION


def share_thresholds(marketplace: Marketplace | None) -> ShareThresholds:
    """Detection share thresholds for the marketplace (#51)."""
    if marketplace == Marketplace.WB:
        return WB_THRESHOLDS
    if marketplace == Marketplace.OZON:
        return OZON_THRESHOLDS
    return GENERIC_THRESHOLDS


def find_fee_reference(header: str) -> FeeReference | None:
    """Match a report column header against the known-fee keywords (#51).

    Fine-looking headers (containing "штраф") consult the fines table
    first so «Штраф за упаковку» resolves to the fine, not the fee.
    """
    lowered = header.lower()
    is_fine = "штраф" in lowered or "penalt" in lowered
    pools = (TYPICAL_FINES, HIDDEN_FEES) if is_fine else (HIDDEN_FEES, TYPICAL_FINES)
    for pool in pools:
        for reference in pool:
            if any(keyword in lowered for keyword in reference.keywords):
                return reference
    return None


def detect_marketplace(filename: str) -> Marketplace | None:
    """Best-effort marketplace guess from the report filename (#51)."""
    lowered = filename.lower()
    if "ozon" in lowered:
        return Marketplace.OZON
    if "wb" in lowered or "wildberries" in lowered:
        return Marketplace.WB
    return None
