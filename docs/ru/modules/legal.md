# Модуль legal

Юридический сканер карточек и документов: детерминированный каталог
правил + LLM-проход по рискам, история сканов в БД.

## Границы

- **Делает:** скан текста/карточек/документов по каталогу правил,
  LLM-ревью в рамках категорий каталога, комплексный аудит бизнеса
  (несколько SKU + свободный текст + документы), персистентную
  историю сканов.
- **Не делает:** не парсит маркетплейсы самостоятельно (адаптер поверх
  analytics), не генерирует тексты, не работает с очередями сам
  (задачи через core/jobs).

## Публичный API

Фабрика: `get_legal_service() -> LegalService` (lru_cache; инжектит
LLM, document parser, card fetch из analytics).

| Метод | Назначение |
|---|---|
| `scan_text(text, *, field, context) -> list[Finding]` | только правила, детерминированно |
| `scan_card(title, description, *, source) -> CardScanReport` | карточка, только правила |
| `async review_text(text, *, context) -> list[Finding]` | LLM-проход; при `LLMError` — деградация до `[]` |
| `ingest_document(filename, data) -> DocumentSections` | байты → текст → секции под лимит LLM |
| `async scan_document(filename, data, *, on_progress) -> DocumentReport` | правила + LLM, слияние |
| `async scan_business(sources, free_text, documents, *, on_progress) -> BusinessScanReport` | комплексный аудит |

Задачи: `legal_scan` (LEGAL_JOB_TYPE; документы грузятся из stash
`legaldocs:{chat_id}`), `legal_card_scan` (LEGAL_CARD_JOB_TYPE;
только правила, без LLM); ретраи 1; `register_legal_jobs()`.
История: `save_scan()`, `load_recent_scans()` (null-pool сессия).

## Схемы

`Severity` (critical/high/medium/low + порядок сортировки),
`RuleCategory` (packaging_marking | prohibited_claims |
mandatory_disclosure), `Rule` (каталог), `Finding` (rule_id пуст для
LLM-находок; excerpt/description/source/field), `CardScanReport`,
`DocumentReport`, `RiskItem`/`RiskOutput` (конверт LLM),
`BusinessScanReport` (cards + documents + skipped + счётчики по
severity), `SkipErrorCode` + `SkippedItem`, `DocumentSections`,
`LegalJobPayload` / `LegalCardPayload`.

## Зависимости

- core: `llm`, `documents`, `stash` (`load_documents`),
  settings (`LEGAL_CARD_CAP`, `LEGAL_DOCUMENT_CAP`),
  `database` (модели `LegalScan`, `LegalDocument`, репозитории).
- analytics: `get_analytics_service().fetch_card` + ошибки парсинга
  (проходят насквозь: `CardNotFoundError`, `CardParseError`,
  `OzonBrowserError`, `UnsupportedMarketplaceError`).

## Кейсы

**Быстрый скан карточки** (`legal_card_scan`): fetch карточки →
детерминированный движок `evaluate_text()` (regex/ключевые слова,
нормализация с сохранением длины, excerpt ±60 символов, максимум 1
находка на правило) → сохранение в историю (scope="card") → JSON.
Без LLM.

**Аудит бизнеса** (`legal_scan`): дедупликация и кап источников
(`LEGAL_CARD_CAP = 10`) → на каждый SKU: fetch + правила + LLM (ошибка
→ `SkippedItem`, общая задача не падает) → свободный текст → до
`LEGAL_DOCUMENT_CAP = 5` документов (парс → секции ≤ 1500 символов, ≤
24 секций → правила + LLM) → счётчики по severity → история.
Прогресс: `scanning_cards` → `scanning_documents` → `llm_review`.

**LLM-риск-проход:** RU system prompt + JSON format →
`extract_json_object` → `RiskOutput` → 1 repair-ретрай; при `LLMError`
— деградация к пустому списку (правила остаются).

## Данные и капы

Каталог: 21 правило R001–R033 (R001–R014 — prohibited_claims,
R020–R022 — mandatory_disclosure только для карточек, R030–R033 —
packaging_marking); `LEGAL_SCAN_RETENTION_DAYS = 90`.
Движок: `MAX_SCAN_LEN = 50_000`; ingestion: `MAX_SECTION_LEN = 1_500`,
`MAX_SECTIONS = 24`; LLM: temp 0.2 / 900 tokens, промпт ≤ 4000
символов, клампы excerpt 200 / описание 300; `_REPAIR_ATTEMPTS = 1`.
Байтовые капы документов — на границе бота
(`LEGAL_DOCUMENT_MAX_BYTES = 10 MiB`).

## Ошибки → RU

`LegalScanError` → RU-текст скана; `LegalDocumentError` →
LEGAL_DOC_UNSUPPORTED / текст ошибки документа; `SkipErrorCode` →
`describe_skip_code(code, source)`.

## Связанные issues/PR

#53–#61 (движок, каталог, сцены, история). Сцены бота:
`handlers/legal.py` (card + audit).
