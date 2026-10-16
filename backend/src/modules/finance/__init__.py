"""Finance module (M5, issues #45-#52).

Deterministic unit economics (manual calculator, what-if scenarios) and
settlement report analysis (column mapping, hidden-fee/fine detection)
on top of versioned reference tariff tables for WB and Ozon.
"""

from src.modules.finance import errors, schemas
from src.modules.finance.calculator import (
    break_even_price,
    calc_unit,
    estimate_costs,
    what_if,
)
from src.modules.finance.errors import FinanceError, ReportParseError
from src.modules.finance.schemas import (
    CostBreakdown,
    FeeFinding,
    FeeKind,
    FinanceReportPayload,
    ProfitabilityReport,
    ReportAnalysis,
    SettlementRow,
    UnitInputs,
)
from src.modules.finance.service import FinanceService, get_finance_service

__all__ = [
    "CostBreakdown",
    "FeeFinding",
    "FeeKind",
    "FinanceError",
    "FinanceReportPayload",
    "FinanceService",
    "ProfitabilityReport",
    "ReportAnalysis",
    "ReportParseError",
    "SettlementRow",
    "UnitInputs",
    "break_even_price",
    "calc_unit",
    "errors",
    "estimate_costs",
    "get_finance_service",
    "schemas",
    "what_if",
]
