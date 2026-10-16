"""Finance service orchestration (issues #45-#52).

Thin deterministic layer over the report mapper, calculator and
detector — no LLM, no network. The bot edge (scene A) calls the
calculator directly; the report analysis (scene B / job) goes through
:class:`FinanceService`.
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal
from functools import lru_cache

from src.modules.finance.calculator import calc_unit, what_if
from src.modules.finance.detector import (
    compute_totals,
    detect_findings,
    effective_commission_pct,
)
from src.modules.finance.report import parse_settlement_report
from src.modules.finance.schemas import (
    ProfitabilityReport,
    ReportAnalysis,
    UnitInputs,
)
from src.modules.finance.tariffs import TARIFFS_AS_OF, detect_marketplace

ProgressCallback = Callable[[str], Awaitable[object]]

PARSING_PROGRESS = "parsing_report"
DETECTING_PROGRESS = "analyzing_fees"


class FinanceService:
    """Deterministic unit economics and settlement report analysis."""

    def calc(self, inputs: UnitInputs) -> ProfitabilityReport:
        """Manual unit-economics report (scene A, #47/#48)."""
        return calc_unit(inputs)

    def what_if(
        self,
        inputs: UnitInputs,
        *,
        price_delta_pct: Decimal = Decimal("0"),
        quantity_delta_pct: Decimal = Decimal("0"),
    ) -> ProfitabilityReport:
        """Re-run the manual report under a price/volume scenario (#47)."""
        return what_if(
            inputs,
            price_delta_pct=price_delta_pct,
            quantity_delta_pct=quantity_delta_pct,
        )

    async def analyze(
        self,
        data: bytes,
        *,
        filename: str,
        on_progress: ProgressCallback | None = None,
    ) -> ReportAnalysis:
        """Parse a settlement report and detect suspicious charges (#49-#51)."""
        if on_progress is not None:
            await on_progress(PARSING_PROGRESS)
        rows = parse_settlement_report(data, filename=filename)
        if on_progress is not None:
            await on_progress(DETECTING_PROGRESS)
        marketplace = detect_marketplace(filename)
        totals = compute_totals(rows)
        return ReportAnalysis(
            filename=filename,
            marketplace=marketplace,
            row_count=len(rows),
            totals=totals,
            findings=detect_findings(rows, totals, marketplace),
            effective_commission_pct=effective_commission_pct(rows, totals),
            tariffs_as_of=TARIFFS_AS_OF.isoformat(),
        )


@lru_cache
def get_finance_service() -> FinanceService:
    """Process-wide singleton (convention of the sibling services)."""
    return FinanceService()
