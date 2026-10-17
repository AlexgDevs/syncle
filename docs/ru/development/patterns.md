# Архитектурные паттерны проекта

Реализация принципов из [principles.md](principles.md) конкретными
механизмами Syncle. Заменяет локальный черновик `ARCHITECTURE.md`
(не коммитится в git). Описывает текущее устройство; решения с
альтернативами выносятся в `docs/adr/`. Бот-специфика (сцены, меню,
клавиатуры) описывается в документации модуля `modules/bot.md`.

## Слои

```
backend/src/
├── bot/        точка входа Telegram (aiogram): handlers/, keyboards/, texts, renderers
├── worker/     точка входа Taskiq-воркер
├── api/        точка входа HTTP (заготовка)
├── modules/    доменная логика (analytics, content, legal, reviews,
│               finance, infographics, user)
└── core/       инфраструктура, не знающая о домене
    ├── settings.py     конфигурация (.env, pydantic-settings)
    ├── http.py         исходящие HTTP-клиенты с retry/proxy (профили)
    ├── llm/            провайдер LLM (OpenAI-совместимый шлюз)
    ├── jobs/           фреймворк фоновых задач (runner + registry)
    ├── documents/      парсер документов (PDF/DOCX/XLSX/CSV)
    ├── database/       SQLAlchemy: base, session, типы
    ├── redis/          клиент Redis
    ├── stash.py        blob-хранилище на Redis (фото, документы, отчёты)
    ├── base/           базовые Repository/Service
    └── logging.py, errors.py, enums.py, results.py
```

Направление импортов: **bot/worker/api → modules → core**.

## Куда класть новый файл

| Что добавляем | Куда |
|---|---|
| Доменный сервис/парсер | `modules/<domain>/` |
| Прайс-листы, тарифы, справочники | `modules/<domain>/tariffs.py`, `constants.py` |
| Промпты LLM | `modules/<domain>/prompts.py` |
| Pydantic-схемы отчётов | `modules/<domain>/schemas.py` |
| Фоновая задача домена | `modules/<domain>/jobs.py` (регистрация) |
| Клавиатуры, тексты, рендеры | `bot/keyboards/`, `bot/texts.py`, `bot/renderers.py` |
| Хендлеры сцен | `bot/handlers/` |
| HTTP-запросы к внешним сервисам | профиль в `core/http.py` |
| Сущность БД | `modules/<domain>/models.py` |
| Новый слой инфраструктуры | `core/` (пакет, когда файлов > 1) |

## Константы: три правила

1. Использует один модуль → приватная `_CONST` в верху этого модуля.
2. Используют 2+ модуля одного пакета → `constants.py` пакета.
3. Меняется при деплое → `core/settings.py` + `.env`.

То же для функций: приватная функция, нужная второму модулю, — сигнал
вынести её в отдельный модуль.

## Паттерн 1. Ports & adapters

Инфраструктура скрыта за протоколами, домен зависит только от порта:

- **`DocumentParser`** (`core/documents/`) — bytes + filename → текст/строки.
  Адаптер `UploadDocumentParser` диспатчит по расширению; домены
  (finance, legal) получают результат, не зная openpyxl/pypdf.
- **`JobRunner`** (`core/jobs/`) — `submit/status/wait`. Реализации:
  `InlineJobRunner` (в памяти, dev) и `TaskiqJobRunner` (Redis + брокер).
  Выбор — `JOBS_MODE` в settings.
- **`ResultSink`** (`bot/delivery.py`) — отправка сообщений доменными
  сервисами без знания aiogram.
- **`ProgressCallback`** — async-колбэк прогресса: сервис шлёт EN-коды
  шагов, бот маппит их в RU через `PROGRESS_STEPS`.
- **HTTP-профили** (`core/http.py::get_client("basket"|"feedbacks"|"ozon")`)
  — каждый внешний сервис со своими таймаутами/ретраями/прокси.

## Паттерн 2. Фоновая задача = лёгкий payload + stash

Джобы никогда не несут байты в payload:

1. Бот кладёт тяжёлое в `core/stash.py` (Redis, TTL 24 ч, байтовые капы).
2. В payload — только `chat_id`, идентификаторы, настройки (JSON).
3. `launch_job_or_inline()`: при `JOBS_MODE=inline` задача выполняется
   синхронно в хендлере (dev), при `taskiq` — через брокер.
4. `bot/polling.py` опрашивает `active_jobs` и доставляет результат
   по `job_type` через реестр рендер/доставки.
5. Ошибки домена → `describe_error()` в `bot/errors.py` → RU-ответ.

Job-only stash-ключи (`documents`, `finreport`) пишутся только в
taskiq-режиме (`_jobs_only()`-гард) — в inline они не читаются.

## Паттерн 3. Ошибки

- Домен бросает `SyncleError`-дерево (`core/errors.py` + `errors.py`
  модуля), исключение несёт machine-readable данные.
- Бот маппит исключение на RU-текст в `bot/errors.py::describe_error`.
- Пользователь никогда не видит traceback или EN-текст ошибки.

## Паттерн 4. Stash и память Redis

- Ключи `syncle:stash:*` и job-ключи — всегда с TTL (24 ч).
- Всё, что пишется из загрузок, имеет байтовый кап
  (`FINANCE_REPORT_MAX_BYTES`, `LEGAL_DOCUMENT_MAX_BYTES`, `PHOTO_MAX_BYTES`).
- `config/redis.conf`: `maxmemory 512mb` + `maxmemory-policy volatile-ttl`
  (эвикция только ключей с TTL); `init_redis` варнит при `maxmemory=0`.
- `active_jobs` (SET) получает TTL на каждом submit.

## Ловушки имён

| Модуль | Что это на самом деле |
|---|---|
| `core/jobs/` | Фреймворк задач: runner, registry, состояния |
| `modules/<d>/jobs.py` | Регистрация обработчиков задач домена |
| `core/http.py` | Исходящие HTTP-клиенты (профили + LLM) |
| `core/stash.py` | Блобы в Redis, не SQL |

## Настройки

`get_settings()` — lru-cached accessor: `.env` парсится один раз при
первом обращении; ленивая инициализация позволяет импортировать модули
без полного `.env` (скрипты, смоуки). `cache_clear()` — в смоуках.

## Шаблон документа модуля (`docs/ru/modules/<name>.md`)

1. **Назначение и границы** — что делает, чего не делает.
2. **Публичный API** — сервисы, функции, схемы (сигнатуры).
3. **Зависимости** — какие core-порты/сервисы использует; stash-ключи,
   job-типы, модели БД.
4. **Кейсы** — happy path + error-пути + прогресс-степы.
5. **Данные** — схемы, ключи Redis, лимиты из settings.
6. **Связанные issues/PR.**
