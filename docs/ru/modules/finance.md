# Модуль finance

Юнит-экономика и разбор отчётов о расчётах WB/Ozon: калькулятор
маржинальности, справочные тарифы, детектор аномальных комиссий.
Полностью детерминирован — без LLM и сети.

## Границы

- **Делает:** расчёт юнит-экономики (what-if сценарии, break-even),
  парсинг settlement-отчётов (XLSX/CSV/PDF), агрегацию итогов,
  сравнение ставок с эталонными тарифами, поиск подозрительных
  списаний.
- **Не делает:** не ходит в маркетплейсы, не использует LLM, не пишет
  в БД/Redis (stash отчёта пишет бот).

## Публичный API

Фабрика: `get_finance_service() -> FinanceService` (lru_cache,
stateless).

| Метод | Назначение |
|---|---|
| `calc(inputs: UnitInputs) -> ProfitabilityReport` | юнит-экономика одной позиции |
| `what_if(inputs, *, price_delta_pct, quantity_delta_pct) -> ProfitabilityReport` | сценарий ±N% от базы |
| `async analyze(data, *, filename, on_progress) -> ReportAnalysis` | разбор отчёта: парс → итоги → находки; прогресс `parsing_report` → `analyzing_fees` |

Задача: `finance_report` (FINANCE_JOB_TYPE), ретраи 1; файл грузится
из stash `finreport:{chat_id}` (`load_report`; просрочка →
`ReportParseError`); `register_finance_jobs()`.

Свободные функции: `calc_unit`, `what_if`, `estimate_costs`,
`break_even_price`; детектор — `compute_totals`, `detect_findings`,
`effective_commission_pct`; тарифы — `commission_range`,
`share_thresholds`, `find_fee_reference`, `detect_marketplace`,
`TARIFFS_AS_OF`.

## Схемы

`UnitInputs` (price, unit_cost, unit_expenses, quantity),
`ProfitabilityReport` (revenue, commission, logistics, storage, fines,
net_profit, margin_pct, break_even_price…), `SettlementRow`
(row_number, period, sales/returns/commissions/logistics/storage/
fines/adjustments, unknown), `FeeFinding`, `ReportAnalysis`
(filename, marketplace, row_count, totals, findings,
effective_commission_pct, tariffs_as_of), `FinanceReportPayload`.

## Зависимости

- core: `stash` (только job-читатель), `documents` (через report.py).
- analytics: enum `Marketplace` / `MARKETPLACE_TITLES` для
  `detect_marketplace` по имени файла.
- llm/http/database: нет.

## Кейсы

**Калькулятор** (всегда inline, без задачи): 4 числовых шага FSM →
`calc()` → отчёт + what-if кнопки (±10% цена/количество через
`what_if()`); копирование результата — copy-кнопка.

**Разбор отчёта** (`finance_report`): загрузка файла (суффикс
.xlsx/.csv/.pdf, кап `FINANCE_REPORT_MAX_BYTES = 10 MiB`) →
`stash_report` → задача: `parse_settlement_report()` (расширение →
`DocumentParser` → поиск шапки по всему документу со scoring;
колонки «Кол-во» не матчатся в sales; стоп на баннере листа) →
`compute_totals` → `detect_findings` (сравнение с тарифами,
допуск `COMMISSION_TOLERANCE_PP = 5`) → `ReportAnalysis` → доставка
сообщением или .md-файлом.

## Данные и капы

- `tariffs.py`: эталон WB/Ozon (`TARIFFS_AS_OF`, действует на
  2026-10-01): WB комиссия 5–40%, логистика ≤ 15%, хранение ≤ 3%;
  Ozon сегменты ≤ 100₽ 17–20%, ≤ 300₽ 23–26%, > 300₽ 20–55%;
  RU-описания скрытых сборов и штрафов — user-facing контент.
- Парсер: `_MIN_MATCHES = 2` (шапка), `_MAX_ROWS = 5_000`; money
  парсится как `Decimal` (RU/EN форматы, скобки для минуса).
- Байтовые капы: отчёт 10 MiB (settings), проверка до/после скачивания.

## Ошибки → RU

`ReportParseError` → FIN_REPORT_EMPTY («нет таблицы с расчётами» и
прочие); `FinanceError` → текст ошибки finance.

## Связанные issues/PR

#45–#52 (M5), багфикс multi-sheet шапки (PR #73). Сцены бота:
`handlers/finance.py`, доставка `bot/finance_delivery.py`. Фикстура:
`backend/tests/fixtures/finansovyy_otchet_wildberries_seller.xlsx`.
