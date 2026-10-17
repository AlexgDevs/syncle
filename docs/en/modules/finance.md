# Module finance

Unit economics and WB/Ozon settlement report analysis: a margin
calculator, reference tariffs, and an anomalous-fee detector.
Fully deterministic — no LLM, no network.

## Boundaries

- **Does:** unit-economics calculation (what-if scenarios,
  break-even), settlement report parsing (XLSX/CSV/PDF), totals
  aggregation, comparing rates against reference tariffs, suspicious
  charge detection.
- **Does not:** call marketplaces, use LLM, write to DB/Redis (the bot
  writes the report stash).

## Public API

Factory: `get_finance_service() -> FinanceService` (lru_cache,
stateless).

| Method | Purpose |
|---|---|
| `calc(inputs: UnitInputs) -> ProfitabilityReport` | single-item unit economics |
| `what_if(inputs, *, price_delta_pct, quantity_delta_pct) -> ProfitabilityReport` | ±N% scenario from the base case |
| `async analyze(data, *, filename, on_progress) -> ReportAnalysis` | report analysis: parse → totals → findings; progress `parsing_report` → `analyzing_fees` |

Job: `finance_report` (FINANCE_JOB_TYPE), 1 retry; the file loads from
stash `finreport:{chat_id}` (`load_report`; expired →
`ReportParseError`); `register_finance_jobs()`.

Free functions: `calc_unit`, `what_if`, `estimate_costs`,
`break_even_price`; detector — `compute_totals`, `detect_findings`,
`effective_commission_pct`; tariffs — `commission_range`,
`share_thresholds`, `find_fee_reference`, `detect_marketplace`,
`TARIFFS_AS_OF`.

## Schemas

`UnitInputs` (price, unit_cost, unit_expenses, quantity),
`ProfitabilityReport` (revenue, commission, logistics, storage, fines,
net_profit, margin_pct, break_even_price…), `SettlementRow`
(row_number, period, sales/returns/commissions/logistics/storage/
fines/adjustments, unknown), `FeeFinding`, `ReportAnalysis`,
`FinanceReportPayload`.

## Dependencies

- core: `stash` (job-side reader), `documents` (via report.py).
- analytics: `Marketplace` / `MARKETPLACE_TITLES` enums for
  `detect_marketplace` by filename.
- llm/http/database: none.

## Use cases

**Calculator** (always inline, no job): four FSM numeric steps →
`calc()` → report + what-if buttons (±10% price/quantity via
`what_if()`); result copying via a copy button.

**Report analysis** (`finance_report`): file upload (suffix
.xlsx/.csv/.pdf, cap `FINANCE_REPORT_MAX_BYTES = 10 MiB`) →
`stash_report` → job: `parse_settlement_report()` (extension →
`DocumentParser` → header search across the whole document with
scoring; «Кол-во» columns never map to sales; stop at sheet banners) →
`compute_totals` → `detect_findings` (tariff comparison,
`COMMISSION_TOLERANCE_PP = 5` tolerance) → `ReportAnalysis` →
delivered as a message or .md file.

## Data and caps

- `tariffs.py`: WB/Ozon reference tables (`TARIFFS_AS_OF`, as of
  2026-10-01): WB commission 5–40%, logistics ≤ 15%, storage ≤ 3%;
  Ozon price segments ≤ 100₽ 17–20%, ≤ 300₽ 23–26%, > 300₽ 20–55%;
  RU descriptions of hidden fees are user-facing content.
- Parser: `_MIN_MATCHES = 2` (header), `_MAX_ROWS = 5_000`; money is
  parsed as `Decimal` (RU/EN formats, parentheses for negatives).
- Byte caps: report 10 MiB (settings), checked before and after
  download.

## Errors → RU

`ReportParseError` → FIN_REPORT_EMPTY ("no tabular data" etc.);
`FinanceError` → finance failure text.

## Related issues/PRs

#45–#52 (M5), multi-sheet header fix (PR #73). Bot scenes:
`handlers/finance.py`, delivery `bot/finance_delivery.py`. Fixture:
`backend/tests/fixtures/finansovyy_otchet_wildberries_seller.xlsx`.
