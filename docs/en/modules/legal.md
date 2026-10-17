# Module legal

Legal scanning of cards and documents: a deterministic rule catalog
plus an LLM risk pass, with scan history in the DB.

## Boundaries

- **Does:** scanning text/cards/documents against the rule catalog,
  LLM review within the catalog's categories, full business audits
  (several SKUs + free text + documents), persistent scan history.
- **Does not:** parse marketplaces itself (an adapter over analytics),
  generate texts, manage queues (jobs via core/jobs).

## Public API

Factory: `get_legal_service() -> LegalService` (lru_cache; injects the
LLM, document parser, and the analytics card fetch).

| Method | Purpose |
|---|---|
| `scan_text(text, *, field, context) -> list[Finding]` | rules only, deterministic |
| `scan_card(title, description, *, source) -> CardScanReport` | card, rules only |
| `async review_text(text, *, context) -> list[Finding]` | LLM pass; degrades to `[]` on `LLMError` |
| `ingest_document(filename, data) -> DocumentSections` | bytes → text → LLM-sized sections |
| `async scan_document(filename, data, *, on_progress) -> DocumentReport` | rules + LLM, merged |
| `async scan_business(sources, free_text, documents, *, on_progress) -> BusinessScanReport` | full audit |

Jobs: `legal_scan` (LEGAL_JOB_TYPE; documents load from stash
`legaldocs:{chat_id}`), `legal_card_scan` (LEGAL_CARD_JOB_TYPE; rules
only, no LLM); 1 retry each; `register_legal_jobs()`. History:
`save_scan()`, `load_recent_scans()` (null-pool session).

## Schemas

`Severity` (critical/high/medium/low + sort order), `RuleCategory`
(packaging_marking | prohibited_claims | mandatory_disclosure),
`Rule` (catalog), `Finding` (empty rule_id for LLM findings;
excerpt/description/source/field), `CardScanReport`,
`DocumentReport`, `RiskItem`/`RiskOutput` (LLM envelope),
`BusinessScanReport` (cards + documents + skipped + severity counts),
`SkipErrorCode` + `SkippedItem`, `DocumentSections`,
`LegalJobPayload` / `LegalCardPayload`.

## Dependencies

- core: `llm`, `documents`, `stash` (`load_documents`), settings
  (`LEGAL_CARD_CAP`, `LEGAL_DOCUMENT_CAP`), `database` (`LegalScan`,
  `LegalDocument` models, repositories).
- analytics: `get_analytics_service().fetch_card` + parsing errors
  pass through (`CardNotFoundError`, `CardParseError`,
  `OzonBrowserError`, `UnsupportedMarketplaceError`).

## Use cases

**Quick card scan** (`legal_card_scan`): fetch card → deterministic
`evaluate_text()` engine (regex/keywords, length-preserving
normalization, ±60-char excerpts, max one finding per rule) → save to
history (scope="card") → JSON. No LLM.

**Business audit** (`legal_scan`): dedupe and cap sources
(`LEGAL_CARD_CAP = 10`) → per SKU: fetch + rules + LLM (failure →
`SkippedItem`, the run continues) → free text → up to
`LEGAL_DOCUMENT_CAP = 5` documents (parse → sections ≤ 1500 chars,
≤ 24 sections → rules + LLM) → severity counts → history.
Progress: `scanning_cards` → `scanning_documents` → `llm_review`.

**LLM risk pass:** RU system prompt + JSON format →
`extract_json_object` → `RiskOutput` → one repair retry; on `LLMError`
— degrade to empty (rules remain).

## Data and caps

Catalog: 21 rules R001–R033 (R001–R014 prohibited_claims, R020–R022
mandatory_disclosure card-only, R030–R033 packaging_marking);
`LEGAL_SCAN_RETENTION_DAYS = 90`. Engine: `MAX_SCAN_LEN = 50_000`;
ingestion: `MAX_SECTION_LEN = 1_500`, `MAX_SECTIONS = 24`; LLM: temp
0.2 / 900 tokens, prompts ≤ 4000 chars, excerpt/description clamps
200/300; `_REPAIR_ATTEMPTS = 1`. Document byte caps live at the bot
edge (`LEGAL_DOCUMENT_MAX_BYTES = 10 MiB`).

## Errors → RU

`LegalScanError` → scan failure text; `LegalDocumentError` →
LEGAL_DOC_UNSUPPORTED / document error text; `SkipErrorCode` →
`describe_skip_code(code, source)`.

## Related issues/PRs

#53–#61 (engine, catalog, scenes, history). Bot scenes:
`handlers/legal.py` (card + audit).
