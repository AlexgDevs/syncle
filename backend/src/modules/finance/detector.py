"""Hidden-charge detector for settlement reports (issue #51).

Pure deterministic logic — the bot only renders the findings. Compares
report totals against the reference tariff tables (#46):

- effective commission above the published range (+ tolerance) →
  ``COMMISSION_OVER`` with the overcharge amount;
- logistics/storage shares above the thresholds → ``LOGISTICS_HIGH`` /
  ``STORAGE_HIGH``;
- per-row fines → ``FINE`` with the source row reference;
- unrecognized numeric columns with net charges, and columns matching
  the known-fee keywords → ``HIDDEN_FEE``.

Finding details are RU — user-facing content (same exception as the
legal catalog); machines keep the structured ``kind``/``amount``.
"""

from dataclasses import dataclass
from decimal import Decimal

from src.modules.analytics.enums import Marketplace
from src.modules.finance.calculator import pct
from src.modules.finance.schemas import (
    FeeFinding,
    FeeKind,
    ProfitabilityReport,
    SettlementRow,
)
from src.modules.finance.tariffs import (
    COMMISSION_TOLERANCE_PP,
    FeeReference,
    commission_range,
    find_fee_reference,
    share_thresholds,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def compute_totals(rows: list[SettlementRow]) -> ProfitabilityReport:
    """Batch P&L from mapped rows (#45/#51).

    Revenue is sales minus returns; COGS/marketing are not part of a
    settlement report; ``other_expenses`` carries the negated signed
    adjustments so the standard profit formula holds.
    """
    revenue = sum((row.sales for row in rows), ZERO) - sum(
        (row.returns for row in rows), ZERO
    )
    commission = sum((row.commissions for row in rows), ZERO)
    logistics = sum((row.logistics for row in rows), ZERO)
    storage = sum((row.storage for row in rows), ZERO)
    fines = sum((row.fines for row in rows), ZERO)
    adjustments = sum((row.adjustments for row in rows), ZERO)
    net = revenue - commission - logistics - storage - fines + adjustments
    return ProfitabilityReport(
        revenue=revenue,
        commission=commission,
        logistics=logistics,
        storage=storage,
        fines=fines,
        other_expenses=-adjustments,
        net_profit=net,
        margin_pct=pct(net, revenue),
        break_even_price=None,
    )


def effective_commission_pct(
    rows: list[SettlementRow], totals: ProfitabilityReport
) -> Decimal | None:
    """Commission as % of gross sales (None when there were no sales)."""
    gross = sum((row.sales for row in rows), ZERO)
    if gross <= ZERO:
        return None
    return (totals.commission / gross * HUNDRED).quantize(Decimal("0.1"))


def _fine_findings(rows: list[SettlementRow]) -> list[FeeFinding]:
    return [
        FeeFinding(
            kind=FeeKind.FINE,
            amount=row.fines,
            source_row=row.row_number,
            detail="Штраф в отчёте — сверьте с причиной в личном кабинете.",
        )
        for row in rows
        if row.fines > ZERO
    ]


def _commission_finding(
    rows: list[SettlementRow],
    totals: ProfitabilityReport,
    marketplace: Marketplace | None,
) -> FeeFinding | None:
    gross = sum((row.sales for row in rows), ZERO)
    if gross <= ZERO or totals.commission <= ZERO:
        return None
    reference = commission_range(marketplace)
    allowed = gross * (reference.max_pct + COMMISSION_TOLERANCE_PP) / HUNDRED
    if totals.commission <= allowed:
        return None
    return FeeFinding(
        kind=FeeKind.COMMISSION_OVER,
        amount=totals.commission - allowed,
        source_row=0,
        detail=(
            f"Эффективная комиссия выше опубликованного диапазона "
            f"до {reference.max_pct}% (+{COMMISSION_TOLERANCE_PP} п.п. допуска): "
            f"проверьте ставку в личном кабинете."
        ),
    )


def _share_finding(
    kind: FeeKind,
    amount_total: Decimal,
    max_share_pct: Decimal,
    gross: Decimal,
    *,
    source_row: int,
    detail: str,
) -> FeeFinding | None:
    if gross <= ZERO or amount_total <= ZERO:
        return None
    allowed = gross * max_share_pct / HUNDRED
    if amount_total <= allowed:
        return None
    return FeeFinding(
        kind=kind,
        amount=amount_total - allowed,
        source_row=source_row,
        detail=detail,
    )


def _unknown_fee_findings(rows: list[SettlementRow]) -> list[FeeFinding]:
    """Aggregate unrecognized columns that carry net charges (#51)."""

    @dataclass
    class ColumnAgg:
        total: Decimal = ZERO
        row: int = 0
        reference: FeeReference | None = None

    per_column: dict[str, ColumnAgg] = {}
    for row in rows:
        for name, value in row.unknown.items():
            entry = per_column.setdefault(name, ColumnAgg(row=row.row_number))
            entry.total += value
            reference = find_fee_reference(name)
            if reference is not None:
                entry.reference = reference
                entry.row = row.row_number
    findings: list[FeeFinding] = []
    for name, entry in per_column.items():
        if entry.reference is None:
            # unknown columns only count when they are net charges
            if entry.total >= ZERO:
                continue
            findings.append(
                FeeFinding(
                    kind=FeeKind.HIDDEN_FEE,
                    amount=abs(entry.total),
                    source_row=entry.row,
                    detail=(
                        f"Неизвестная колонка «{name}» со списаниями — "
                        f"проверьте, что это за сбор."
                    ),
                )
            )
            continue
        findings.append(
            FeeFinding(
                kind=FeeKind.HIDDEN_FEE,
                amount=abs(entry.total),
                source_row=entry.row,
                detail=entry.reference.description,
            )
        )
    return findings


def detect_findings(
    rows: list[SettlementRow],
    totals: ProfitabilityReport,
    marketplace: Marketplace | None,
) -> list[FeeFinding]:
    """Run all checks and return findings sorted by amount desc (#51)."""
    gross = sum((row.sales for row in rows), ZERO)
    thresholds = share_thresholds(marketplace)
    findings: list[FeeFinding] = []
    findings.extend(_fine_findings(rows))
    commission_finding = _commission_finding(rows, totals, marketplace)
    if commission_finding is not None:
        findings.append(commission_finding)
    logistics_finding = _share_finding(
        FeeKind.LOGISTICS_HIGH,
        totals.logistics,
        thresholds.max_logistics_share_pct,
        gross,
        source_row=0,
        detail=(
            f"Логистика превышает {thresholds.max_logistics_share_pct}% продаж — "
            f"возможно, в отчёт попали сборы сверх тарифа."
        ),
    )
    if logistics_finding is not None:
        findings.append(logistics_finding)
    storage_finding = _share_finding(
        FeeKind.STORAGE_HIGH,
        totals.storage,
        thresholds.max_storage_share_pct,
        gross,
        source_row=0,
        detail=(
            f"Хранение превышает {thresholds.max_storage_share_pct}% продаж — "
            f"проверьте остатки и коэффициенты склада."
        ),
    )
    if storage_finding is not None:
        findings.append(storage_finding)
    findings.extend(_unknown_fee_findings(rows))
    findings.sort(key=lambda item: item.amount, reverse=True)
    return findings
