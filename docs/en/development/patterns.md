# Architectural Patterns

How the principles from [principles.md](principles.md) are implemented
in Syncle's concrete mechanisms. Replaces the local `ARCHITECTURE.md`
draft (not committed to git). Describes the current setup; decisions
with alternatives go to `docs/adr/`. Bot specifics (scenes, menus,
keyboards) are documented in the module doc `modules/bot.md`.

## Layers

```
backend/src/
├── bot/        Telegram entry point (aiogram): handlers/, keyboards/, texts, renderers
├── worker/     Taskiq worker entry point
├── api/        HTTP entry point (scaffold)
├── modules/    domain logic (analytics, content, legal, reviews,
│               finance, infographics, user)
└── core/       infrastructure, domain-agnostic
    ├── settings.py     configuration (.env, pydantic-settings)
    ├── http.py         outbound HTTP clients with retry/proxy (profiles)
    ├── llm/            LLM provider (OpenAI-compatible gateway)
    ├── jobs/           background job framework (runner + registry)
    ├── documents/      document parser (PDF/DOCX/XLSX/CSV)
    ├── database/       SQLAlchemy: base, session, types
    ├── redis/          Redis client
    ├── stash.py        Redis blob store (photos, documents, reports)
    ├── base/           base Repository/Service
    └── logging.py, errors.py, enums.py, results.py
```

Import direction: **bot/worker/api → modules → core**.

## Where to put a new file

| What | Where |
|---|---|
| Domain service/parser | `modules/<domain>/` |
| Price lists, tariffs, reference data | `modules/<domain>/tariffs.py`, `constants.py` |
| LLM prompts | `modules/<domain>/prompts.py` |
| Pydantic report schemas | `modules/<domain>/schemas.py` |
| Domain background job | `modules/<domain>/jobs.py` (registration) |
| Keyboards, texts, renderers | `bot/keyboards/`, `bot/texts.py`, `bot/renderers.py` |
| Scene handlers | `bot/handlers/` |
| Outbound HTTP calls | profile in `core/http.py` |
| DB entity | `modules/<domain>/models.py` |
| New infrastructure layer | `core/` (package once >1 file) |

## Constants: three rules

1. Used by one module → private `_CONST` at the top of that module.
2. Used by 2+ modules of one package → the package's `constants.py`.
3. Changes on deploy → `core/settings.py` + `.env`.

Same for functions: a private function needed by a second module is a
signal to extract it.

## Pattern 1. Ports & adapters

Infrastructure is hidden behind protocols; domains depend on ports only:

- **`DocumentParser`** (`core/documents/`) — bytes + filename → text/rows.
  The `UploadDocumentParser` adapter dispatches on extension; domains
  (finance, legal) consume the result without knowing openpyxl/pypdf.
- **`JobRunner`** (`core/jobs/`) — `submit/status/wait`. Implementations:
  `InlineJobRunner` (in-memory, dev) and `TaskiqJobRunner` (Redis +
  broker). Selected by the `JOBS_MODE` setting.
- **`ResultSink`** (`bot/delivery.py`) — message delivery from domain
  services without aiogram knowledge.
- **`ProgressCallback`** — async progress hook: services emit EN step
  codes; the bot maps them to RU via `PROGRESS_STEPS`.
- **HTTP profiles** (`core/http.py::get_client("basket"|"feedbacks"|"ozon")`)
  — one client per external service with its own timeouts/retries/proxy.

## Pattern 2. Background job = light payload + stash

Jobs never carry bytes in the payload:

1. The interface layer puts heavy data into `core/stash.py` (Redis,
   24 h TTL, byte caps).
2. The payload holds only `chat_id`, identifiers, settings (JSON).
3. `launch_job_or_inline()`: with `JOBS_MODE=inline` the task runs
   synchronously in the handler (dev); with `taskiq` — via the broker.
4. The bot's polling loop polls `active_jobs` and delivers results by
   `job_type` through the render/delivery registry.
5. Domain errors → `describe_error()` in `bot/errors.py` → RU reply.

Job-only stash keys (`documents`, `finreport`) are written only in
taskiq mode (`_jobs_only()` guard) — inline never reads them.

## Pattern 3. Errors

- Domains raise from the `SyncleError` tree (`core/errors.py` + the
  module's `errors.py`); exceptions carry machine-readable data.
- The bot maps exceptions to RU text in `bot/errors.py::describe_error`.
- Users never see tracebacks or EN error text.

## Pattern 4. Stash and Redis memory

- `syncle:stash:*` and job keys always carry a TTL (24 h).
- Anything written from uploads has a byte cap (`FINANCE_REPORT_MAX_BYTES`,
  `LEGAL_DOCUMENT_MAX_BYTES`, `PHOTO_MAX_BYTES`).
- `config/redis.conf`: `maxmemory 512mb` + `maxmemory-policy volatile-ttl`
  (evict only TTL keys); `init_redis` warns when `maxmemory` is 0.
- The `active_jobs` (SET) gets a TTL refreshed on every submit.

## Naming traps

| Module | What it actually is |
|---|---|
| `core/jobs/` | Job framework: runner, registry, states |
| `modules/<d>/jobs.py` | Domain job handler registration |
| `core/http.py` | Outbound HTTP clients (profiles + LLM) |
| `core/stash.py` | Redis blobs, not SQL |

## Settings

`get_settings()` is an lru-cached accessor: `.env` is parsed once on
first access; lazy initialization lets modules be imported without a
full `.env` (scripts, smokes). `cache_clear()` is used in smokes.

## Module doc template (`docs/ru/modules/<name>.md`)

1. **Purpose and boundaries** — what it does, what it does not.
2. **Public API** — services, functions, schemas (signatures).
3. **Dependencies** — core ports/services used; stash keys, job types,
   DB models.
4. **Use cases** — happy path + error paths + progress steps.
5. **Data** — schemas, Redis keys, settings limits.
6. **Related issues/PRs.**
