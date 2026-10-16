"""Unit-economics calculator (issue #47).

Deterministic Decimal math — no LLM, no I/O. Computes profit, margin
and break-even price for manual inputs (#48) and re-runs them under
what-if scenarios (price up/down, volume change). Commission-aware
scenarios take a percentage point rate — callers can resolve it from the
reference tariff tables (``tariffs.commission_range``, #46).
"""

from decimal import Decimal, ROUND_HALF_UP

from src.modules.finance.schemas import (
    CostBreakdown,
    ProfitabilityReport,
    UnitInputs,
)

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
_CENT = Decimal("0.01")

_PCT_PLACES = Decimal("0.1")  # margin keeps one decimal place
_MONEY_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Round to kopecks, half-up."""
    return value.quantize(_MONEY_PLACES, rounding=ROUND_HALF_UP)


def pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Percentage with one decimal place; 0 when the denominator is 0."""
    if denominator == ZERO:
        return ZERO
    return (numerator / denominator * HUNDRED).quantize(
        _PCT_PLACES, rounding=ROUND_HALF_UP
    )


def break_even_price(
    unit_cost: Decimal, unit_expenses: Decimal, commission_pct: Decimal = ZERO
) -> Decimal:
    """Per-unit price where net profit is 0.

    ``commission_pct`` models fees proportional to the price (percent of
    sale) that are *not* part of ``unit_expenses``: solving
    ``price = cost + expenses + price * rate`` gives
    ``price = (cost + expenses) / (1 - rate)``.
    """
    rate = commission_pct / HUNDRED
    if rate >= ONE:
        # commission eats the whole price: never breaks even
        return ZERO
    base = unit_cost + unit_expenses
    return money(base / (ONE - rate))


def _build_report(
    inputs: UnitInputs,
    *,
    commission: Decimal,
    other_expenses: Decimal,
    commission_pct: Decimal = ZERO,
) -> ProfitabilityReport:
    revenue = money(inputs.price * inputs.quantity)
    cogs = money(inputs.unit_cost * inputs.quantity)
    commission = money(commission)
    other = money(other_expenses)
    net = money(revenue - cogs - commission - other)
    return ProfitabilityReport(
        revenue=revenue,
        cogs=cogs,
        commission=commission,
        other_expenses=other,
        net_profit=net,
        margin_pct=pct(net, revenue),
        break_even_price=break_even_price(
            inputs.unit_cost, inputs.unit_expenses, commission_pct
        ),
    )


def calc_unit(
    inputs: UnitInputs, *, commission_pct: Decimal = ZERO
) -> ProfitabilityReport:
    """Profit, margin and break-even for the manual inputs (#47/#48).

    ``commission_pct`` splits a price-proportional commission out of the
    report: the commission line is computed from revenue while
    ``unit_expenses`` covers the remaining (non-commission) expenses.
    With the default 0 the whole expense lump lands in
    ``other_expenses`` — exactly what scene A collects.
    """
    commission = inputs.price * inputs.quantity * commission_pct / HUNDRED
    return _build_report(
        inputs,
        commission=commission,
        other_expenses=inputs.unit_expenses * inputs.quantity,
        commission_pct=commission_pct,
    )


def what_if(
    inputs: UnitInputs,
    *,
    commission_pct: Decimal = ZERO,
    price_delta_pct: Decimal = ZERO,
    quantity_delta_pct: Decimal = ZERO,
) -> ProfitabilityReport:
    """Recompute under a scenario (#47): price and/or volume shift.

    Deltas are percentage points of the original values (10 = +10%,
    -10 = -10%). Unit cost and per-unit expenses stay unchanged.
    """
    price = inputs.price * (ONE + price_delta_pct / HUNDRED)
    quantity = inputs.quantity * (ONE + quantity_delta_pct / HUNDRED)
    scenario = inputs.model_copy(
        update={"price": money(price), "quantity": money(quantity)}
    )
    return calc_unit(scenario, commission_pct=commission_pct)


def estimate_costs(
    revenue: Decimal,
    commission_pct: Decimal,
    per_unit_logistics: Decimal,
    per_unit_storage: Decimal,
    quantity: Decimal,
) -> CostBreakdown:
    """Tariff-estimated batch deductions (#46/#47).

    ``commission_pct`` comes from ``tariffs.commission_range``; logistics
    and storage are per-unit amounts (volume/days are seller-specific).
    """
    return CostBreakdown(
        commission=money(revenue * commission_pct / HUNDRED),
        logistics=money(quantity * per_unit_logistics),
        storage=money(quantity * per_unit_storage),
    )
