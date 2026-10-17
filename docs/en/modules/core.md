# Core Module

The infrastructure layer that knows nothing about the domain. Core
public ports are used by every module and entry point (bot, worker,
api).

## Boundaries

- **Does:** configuration, Redis, blob store (stash), job framework,
  document parser, HTTP clients, LLM gateway, DB, base
  Repository/Service, logging, base error tree.
- **Does not:** import `src.modules` or entry points (layer rule see
  [principles.md](../development/principles.md)); hold domain concepts
  (cards, reviews, reports).

## Sections

### settings.py — configuration

`get_settings()` is an lru-cached accessor: `.env` is parsed once,
lazily. The full parameter table lives in
[configuration.md](../configuration.md).

Public API: `get_settings() -> Settings` (all access via
`settings.<FIELD>`; reading os.environ directly is forbidden).

### redis/ — client

- `init_redis() -> Redis` — pool from `REDIS_*`, `ping()`, warns when
  `maxmemory == 0` (memory is guarded by `config/redis.conf`).
- `get_redis() -> Redis` — singleton; raises if not initialized.
- `close_redis(client)` — closes the pool (bot/worker shutdown hooks).

Depends on: `REDIS_URL`, `REDIS_MAX_CONNECTIONS`, socket timeouts.

### stash.py — Redis blob store

Heavy data (photos, documents, reports) lives in the stash, not in job
payloads. All keys are `syncle:stash:*`, TTL = `STASH_TTL_SECONDS`
(24 h); all writes are best-effort (failure → log + degradation, not a
crash).

| Key | API | Written by | Read by |
|---|---|---|---|
| `seo:{chat_id}` | `stash_seo`, `load_stashed_entry` → `StashEntry(seo, photos)`, `load_stashed_seo` | bot after SEO generation | infographics job |
| `infobrief:{chat_id}` | `stash_brief`, `load_brief` → `BriefEntry` | infographics scene | infographics job |
| `legaldocs:{chat_id}` | `stash_documents`, `load_documents` → `list[(filename, bytes)]` | audit scene (taskiq only, `_jobs_only()`) | `legal_scan` job |
| `finreport:{chat_id}` | `stash_report`, `load_report` → `(filename, bytes)` | report scene (taskiq only) | `finance_report` job |

Job-only keys (`legaldocs`, `finreport`) are not written under
`JOBS_MODE=inline` — nothing reads them in that mode.

### jobs/ — background job framework

- `base.py` — the `BackgroundJobRunner` port (`submit/status/cancel`),
  `JobContext` (`progress(step)`, `cancelled()`), `JobHandler`,
  `JobInfo`, states `JobState`
  (`pending/running/done/failed/cancelled`), keys `syncle:job:{id}` and
  `syncle:jobs:active`.
- `asyncio_runner.py` — `AsyncioJobRunner`: in-memory reference
  (state lost on restart).
- `taskiq_runner.py` — `TaskiqJobRunner`: Redis hash
  (id/job_type/state/payload/progress/result/error), active SET with
  TTL `JOB_TTL_SECONDS` (24 h, refreshed on every submit), broker
  `ListQueueBroker(REDIS_URL)`; the `run_analysis` task invokes the
  registry handler with `_RedisJobContext` (progress written to the
  hash, cancellation via checkpoints).
- `registry.py` — `register_job_handlers(handlers, retries)`,
  `get_job_handler(job_type)`, `get_job_retries` (default 0; modules
  set 1).

Payload contract: JSON-serializable and light (chat_id, identifiers,
settings); bytes only via the stash. `extra="ignore"` in schemas is
deliberate: the bot appends delivery metadata.

**Worker** (`src/worker/app.py`) — the composition root:
`uv run taskiq worker src.worker.app:broker`. At import time it
registers every module's jobs (`analysis`, `niche_scan`, `seo_text`,
`reviews_analysis`, `infographics_render`, `finance_report`,
`legal_scan`, `legal_card_scan`); startup/shutdown — `init_redis` /
`close_redis`.

### documents/ — document parser

The `DocumentParser.parse(data, *, filename) -> ParsedDocument(text,
rows, pages)` port. The `UploadDocumentParser` adapter dispatches on
extension: PDF (pypdf), DOCX (python-docx), XLSX (openpyxl, all sheets
concatenated into one row stream), CSV (encoding probe: utf-8-sig,
cp1251, utf-16, latin-1).

Caps: `MAX_TEXT_LEN = 200_000` chars, `MAX_ROWS / MAX_ROWS_SHEET =
5_000`. Errors: `DocumentParseError`, `UnsupportedDocumentError`.

Factory: `get_document_parser()` (lru_cache). Used by finance (report
parsing) and legal (audit documents).

### http.py — outbound HTTP clients

- `get_client(profile)` for `basket` / `feedbacks` / `ozon`: httpx with
  `RetryTransport` (exponential backoff on timeouts and 5xx, 4 s cap),
  `HTTP_TIMEOUT`, browser headers. The `ozon` profile goes through
  `PROXY_URL` when set.
- `get_llm_client()` — client for the OpenAI-compatible SDK (the SDK
  retries itself).

Reads: `HTTP_TIMEOUT`, `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_BASE`,
`PROXY_URL`.

### llm/ — LLM provider

- Ports: `LLMProvider.complete(prompt, system, temperature, max_tokens,
  images)` and `ImageProvider.generate_image(prompt, size, images)`.
- Factories (lru_cache, `None` when unconfigured):
  `get_llm_provider()`, `get_vision_provider()`
  (`LLM_VISION_MODEL` falling back to `LLM_MODEL`),
  `get_image_provider()` — with `AITUNNEL_API_KEY` set, AITunnel owns
  image generation (image-only), otherwise the OpenAI-compatible
  gateway (`LLM_IMAGE_*`).
- Errors: `LLMError` ⊂ `SyncleError`; subtypes `LLMTimeoutError`,
  `LLMRateLimitError`, `LLMUnavailableError`.
- `json_output.extract_json_object(raw)` — tolerant JSON extractor
  from LLM outputs (shared by all LLM-output modules).

### database/ — SQLAlchemy

`get_engine()`, `get_null_pool_engine()`, `get_session_factory()`,
`get_null_pool_session_factory()`, DI generator `get_session()`.
`UUIDBase` (UUID pk + timestamps), types `int_pk/str_128/...`.
Reads `DATABASE_URL` (computed from `POSTGRES_*`).

### base/ — base classes

`BaseRepository[T: UUIDBase]` (`get_filtered/get_one/add/update/
delete`), `BaseService` (holds an `AsyncSession`). Used by legal
(scan history) and user repositories.

### errors.py / logging.py / results.py / enums.py

- `SyncleError` — the error-tree root; messages are EN, the bot adapter
  translates to RU (`describe_error`).
- `setup_logging(level)` — plain-text format.
- `ResultSink` — delivery port (`deliver/deliver_file/deliver_photo`);
  the `AiogramResultSink` adapter lives in `bot/delivery.py`.
- `JobState` — StrEnum of job states.

## Module → core dependency map

| Module | Uses |
|---|---|
| analytics | http (basket/feedbacks), llm, settings (caps, price, OZON_CDP_URL) |
| content (SEO) | llm |
| infographics | llm (text+image), stash (seo/infobrief), settings (AITUNNEL_*) |
| legal | llm, documents, stash (legaldocs), settings (LEGAL_*), database (history) |
| reviews | llm, analytics (fetch) |
| finance | stash (finreport), documents (via report.py) |
| user | database, base |

## Related issues/PRs

#15 (DocumentParser), #17 (HTTP), #20 (jobs), ADR-002 (LLM
exceptions), ADR-004 (price parsing); plan A memory guards (PR #73).
