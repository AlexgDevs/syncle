# Модуль core

Инфраструктурный слой, не знающий о домене. Публичные порты core
используются всеми модулями и точками входа (bot, worker, api).

## Границы

- **Делает:** конфигурация, Redis, blob-хранилище (stash), фреймворк
  задач, парсер документов, HTTP-клиенты, LLM-шлюз, БД, базовые
  Repository/Service, логирование, базовое дерево ошибок.
- **Не делает:** не импортирует `src.modules` и точки входа (правило
  слоёв см. [principles.md](../development/principles.md)); не содержит
  доменных понятий (карточек, отзывов, отчётов).

## Секции

### settings.py — конфигурация

`get_settings()` — lru-cached accessor: `.env` парсится один раз,
ленивая инициализация. Полная таблица параметров — в
[configuration.md](../configuration.md).

Публичный API: `get_settings() -> Settings` (все обращения через
`settings.<FIELD>`; прямое чтение os.environ запрещено).

### redis/ — клиент

- `init_redis() -> Redis` — пул из `REDIS_*`, `ping()`, warning при
  `maxmemory == 0` (память защищена `config/redis.conf`).
- `get_redis() -> Redis` — singleton; падает, если не инициализирован.
- `close_redis(client)` — закрытие пула (shutdown-хуки bot/worker).

Зависимости: `REDIS_URL`, `REDIS_MAX_CONNECTIONS`, таймауты.

### stash.py — blob-хранилище на Redis

Большие данные (фото, документы, отчёты) живут в stash, не в payload
задач. Все ключи — `syncle:stash:*`, TTL = `STASH_TTL_SECONDS` (24 ч);
все записи best-effort (ошибка — лог и деградация, не падение).

| Ключ | API | Пишется | Читает |
|---|---|---|---|
| `seo:{chat_id}` | `stash_seo`, `load_stashed_entry` → `StashEntry(seo, photos)`, `load_stashed_seo` | бот после генерации SEO | job инфографики |
| `infobrief:{chat_id}` | `stash_brief`, `load_brief` → `BriefEntry` | бот инфографики | job инфографики |
| `legaldocs:{chat_id}` | `stash_documents`, `load_documents` → `list[(filename, bytes)]` | бот аудита (только taskiq, `_jobs_only()`) | job `legal_scan` |
| `finreport:{chat_id}` | `stash_report`, `load_report` → `(filename, bytes)` | бот финотчёта (только taskiq) | job `finance_report` |

Job-only ключи (`legaldocs`, `finreport`) не пишутся при
`JOBS_MODE=inline` — в этом режиме их никто не читает.

### jobs/ — фреймворк фоновых задач

- `base.py` — порт `BackgroundJobRunner` (`submit/status/cancel`),
  `JobContext` (`progress(step)`, `cancelled()`), `JobHandler`,
  `JobInfo`, состояния `JobState` (`pending/running/done/failed/
  cancelled`), ключи `syncle:job:{id}` и `syncle:jobs:active`.
- `asyncio_runner.py` — `AsyncioJobRunner`: in-memory референс
  (состояние теряется при рестарте).
- `taskiq_runner.py` — `TaskiqJobRunner`: hash в Redis
  (id/job_type/state/payload/progress/result/error), active-SET с TTL
  `JOB_TTL_SECONDS` (24 ч, обновляется на каждом submit), брокер
  `ListQueueBroker(REDIS_URL)`, задача `run_analysis` вызывает
  handler из registry с `_RedisJobContext` (прогресс пишется в hash,
  отмена — checkpoint).
- `registry.py` — `register_job_handlers(handlers, retries)`,
  `get_job_handler(job_type)`, `get_job_retries` (по умолчанию 0;
  модули ставят 1).

Контракт payload: JSON-сериуемый и лёгкий (chat_id, идентификаторы,
настройки); байты — только через stash. `extra="ignore"` в схемах
намеренно: бот дописывает delivery-метаданные.

**Worker** (`src/worker/app.py`) — composition root:
`uv run taskiq worker src.worker.app:broker`. На import регистрирует
задачи всех модулей (`analysis`, `niche_scan`, `seo_text`,
`reviews_analysis`, `infographics_render`, `finance_report`,
`legal_scan`, `legal_card_scan`); startup/shutdown — `init_redis` /
`close_redis`.

### documents/ — парсер документов

Порт `DocumentParser.parse(data, *, filename) -> ParsedDocument(text,
rows, pages)`. Адаптер `UploadDocumentParser` диспатчит по расширению:
PDF (pypdf), DOCX (python-docx), XLSX (openpyxl, все листы
склеиваются в один поток строк), CSV (проба кодировок utf-8-sig,
cp1251, utf-16, latin-1).

Капы: `MAX_TEXT_LEN = 200_000` символов, `MAX_ROWS / MAX_ROWS_SHEET =
5_000`. Ошибки: `DocumentParseError`, `UnsupportedDocumentError`.

Фабрика: `get_document_parser()` (lru_cache). Используют: finance
(разбор отчёта), legal (разбор документов аудита).

### http.py — исходящие HTTP-клиенты

- `get_client(profile)` для `basket` / `feedbacks` / `ozon`: httpx с
  `RetryTransport` (exponential backoff, таймауты и 5xx, кап 4 с),
  таймаут `HTTP_TIMEOUT`, браузерные заголовки. Профиль `ozon`
  проходит через `PROXY_URL`, если задан.
- `get_llm_client()` — клиент под OpenAI-совместимый SDK (ретраи
  делает сам SDK).

Читает: `HTTP_TIMEOUT`, `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_BASE`,
`PROXY_URL`.

### llm/ — провайдер LLM

- Порты: `LLMProvider.complete(prompt, system, temperature, max_tokens,
  images)` и `ImageProvider.generate_image(prompt, size, images)`.
- Фабрики (lru_cache, `None` когда не настроено):
  `get_llm_provider()`, `get_vision_provider()`
  (`LLM_VISION_MODEL` c фолбэком на `LLM_MODEL`),
  `get_image_provider()` — при заданном `AITUNNEL_API_KEY` приоритет
  у AITunnel (image-only), иначе OpenAI-совместимый шлюз
  (`LLM_IMAGE_*`).
- Ошибки: `LLMError` ⊂ `SyncleError`; подтипы `LLMTimeoutError`,
  `LLMRateLimitError`, `LLMUnavailableError`.
- `json_output.extract_json_object(raw)` — толерантный вырезальщик
  JSON из ответов LLM (общий для всех модулей с LLM-выводом).

### database/ — SQLAlchemy

`get_engine()`, `get_null_pool_engine()`, `get_session_factory()`,
`get_null_pool_session_factory()`, DI-генератор `get_session()`.
`UUIDBase` (UUID pk + timestamps), типы `int_pk/str_128/...`.
Читает `DATABASE_URL` (computed из `POSTGRES_*`).

### base/ — базовые классы

`BaseRepository[T: UUIDBase]` (`get_filtered/get_one/add/update/
delete`), `BaseService` (держит `AsyncSession`). Используются
репозиториями legal (история сканов) и user.

### errors.py / logging.py / results.py / enums.py

- `SyncleError` — корень дерева ошибок; сообщения EN, адаптер бота
  переводит в RU (`describe_error`).
- `setup_logging(level)` — plain-text format.
- `ResultSink` — порт доставки (`deliver/deliver_file/deliver_photo`);
  адаптер `AiogramResultSink` живёт в `bot/delivery.py`.
- `JobState` — StrEnum состояний задач.

## Зависимости модулей от core (карта)

| Модуль | Использует |
|---|---|
| analytics | http (basket/feedbacks), llm, settings (капы, price, OZON_CDP_URL) |
| content (SEO) | llm |
| infographics | llm (text+image), stash (seo/infobrief), settings (AITUNNEL_*) |
| legal | llm, documents, stash (legaldocs), settings (LEGAL_*), database (history) |
| reviews | llm, analytics (fetch) |
| finance | stash (finreport), documents (через report.py) |
| user | database, base |

## Связанные issues/PR

#15 (DocumentParser), #17 (HTTP), #20 (jobs), ADR-002 (LLM
исключения), ADR-004 (price parsing); plan A memory guards (PR #73).
