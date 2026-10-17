# Конфигурация (.env)

Все параметры `backend/.env` — класс `Settings` (`src/core/settings.py`,
pydantic-settings). Пустые значения игнорируются (`env_ignore_empty`);
неизвестные ключи не вызывают ошибку (`extra="ignore"`).

`.env` не коммитится в git. Локально заполняется по этой таблице.

## Обязательные параметры

| Параметр | Назначение |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | доступ к Postgres; из них вычисляется `DATABASE_URL` (`computed_field`) |
| `BOT_TOKEN` | токен Telegram-бота |

## База данных и логирование

| Параметр | Дефолт | Назначение |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | хост Postgres |
| `POSTGRES_PORT` | `5432` | порт Postgres |
| `LOG_LEVEL` | `INFO` | уровень stdlib-логирования |

## LLM (OpenAI-совместимый шлюз)

| Параметр | Дефолт | Назначение |
|---|---|---|
| `LLM_API_KEY` | `""` | ключ шлюза; пусто ⇒ провайдеры возвращают `None`, LLM-фичи недоступны |
| `LLM_BASE_URL` | `https://api.proxyapi.ru/openai/v1` | базовый URL текстового шлюза |
| `LLM_MODEL` | `""` | текстовая модель; пусто ⇒ LLM недоступен |
| `LLM_TIMEOUT` | `30.0` | таймаут LLM-запроса, с |
| `LLM_VISION_MODEL` | `""` | vision-модель; фолбэк на `LLM_MODEL` |
| `LLM_IMAGE_MODEL` | `""` | image-модель (фолбэка нет); пусто ⇒ генерация картинок через этот шлюз недоступна |
| `LLM_IMAGE_BASE_URL` | `""` | отдельный базовый URL для картинок; `""` ⇒ тот же, что `LLM_BASE_URL` |
| `LLM_IMAGE_QUALITY` | `""` | качество `gpt-image*` (`low/medium/high`); `""` ⇒ не передаётся |

### AITunnel (приоритетный image-провайдер)

| Параметр | Дефолт | Назначение |
|---|---|---|
| `AITUNNEL_API_KEY` | `""` | когда задан — генерация картинок идёт через AITunnel (Gemini), а не через `LLM_IMAGE_*` |
| `AITUNNEL_IMAGE_MODEL` | `gemini-3.1-flash-lite-image` | модель AITunnel |
| `AITUNNEL_IMAGE_BASE_URL` | `https://api.aitunnel.ru/v1` | базовый URL AITunnel |

## Исходящий HTTP

| Параметр | Дефолт | Назначение |
|---|---|---|
| `HTTP_TIMEOUT` | `10.0` | таймаут HTTP-клиентов, с |
| `HTTP_MAX_RETRIES` | `2` | число ретраев (всего попыток = retries + 1) |
| `HTTP_BACKOFF_BASE` | `0.5` | база exponential backoff (кап 4 с) |
| `PROXY_URL` | `""` | прокси для профиля `ozon`; `""` ⇒ напрямую |

## Redis

| Параметр | Дефолт | Назначение |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | адрес Redis (и брокера Taskiq) |
| `REDIS_MAX_CONNECTIONS` | `10` | размер пула |
| `REDIS_SOCKET_TIMEOUT` | `5.0` | таймаут сокета, с |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `5.0` | таймаут connect, с |
| `REDIS_RETRY_ON_TIMEOUT` | `False` | ретраи клиента по таймауту |

Память Redis ограничивается не здесь, а `backend/config/redis.conf`
(`maxmemory 512mb`, `maxmemory-policy volatile-ttl`).

## Задачи (jobs)

| Параметр | Дефолт | Назначение |
|---|---|---|
| `JOBS_MODE` | `inline` | `inline` — задачи выполняются синхронно в хендлере (dev); `taskiq` — через воркер. В taskiq-режиме включается запись job-only stash-ключей (документы, финотчёт) и запуск `JobPoller` |
| `JOBS_POLL_INTERVAL` | `2.0` | интервал опроса active-jobs, с |

## Парсинг цен (Playwright) и Ozon CDP

| Параметр | Дефолт | Назначение |
|---|---|---|
| `PRICE_ENABLED` | `True` | включает эскалацию цены через рендер страницы (Playwright) |
| `PRICE_HEADLESS` | `False` | WB антидетект требует headed-режим |
| `PRICE_TIMEOUT` | `45.0` | таймаут браузерной сцены, с |
| `PROXY_ROTATE_URL` | `""` | URL ротации прокси для браузера (опционально) |
| `OPTIMAL_PRICE_UNDERCUT_PCT` | `3.0` | насколько optimal price ниже цены конкурента, % |
| `OZON_CDP_URL` | `http://127.0.0.1:9336` | адрес реального Edge-браузера для Ozon (CDP) |

## Капы (лимиты)

| Параметр | Дефолт | Назначение |
|---|---|---|
| `REVIEWS_CAP` | `50` | максимум отзывов на один fetch |
| `NICHE_ITEM_CAP` | `30` | максимум позиций ниши с одного маркетплейса |
| `LEGAL_CARD_CAP` | `10` | максимум SKU/ссылок за один аудит |
| `LEGAL_DOCUMENT_CAP` | `5` | максимум документов за один аудит |
| `LEGAL_DOCUMENT_MAX_BYTES` | `10 MiB` | байтовый кап одного документа (проверяется до и после скачивания) |
| `FINANCE_REPORT_MAX_BYTES` | `10 MiB` | байтовый кап финансового отчёта |

Капы вне settings: `PHOTO_MAX_BYTES = 5 MiB` (`bot/photos.py`),
`MAX_TEXT_LEN = 200_000` / `MAX_ROWS = 5_000` (core/documents),
`REPORT_LIMIT = 4000` символов «сообщение vs файл» (`bot/renderers.py`).

## Как меняются параметры

Любое изменение дефолта или нового параметра — правка
`src/core/settings.py` + этой таблицы в том же PR.
