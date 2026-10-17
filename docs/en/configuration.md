# Configuration (.env)

All parameters of `backend/.env` — the `Settings` class
(`src/core/settings.py`, pydantic-settings). Empty values are ignored
(`env_ignore_empty`); unknown keys do not raise (`extra="ignore"`).

`.env` is never committed. Locally it is filled using this table.

## Required parameters

| Parameter | Purpose |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres access; `DATABASE_URL` is computed from them (`computed_field`) |
| `BOT_TOKEN` | Telegram bot token |

## Database and logging

| Parameter | Default | Purpose |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | Postgres host |
| `POSTGRES_PORT` | `5432` | Postgres port |
| `LOG_LEVEL` | `INFO` | stdlib logging level |

## LLM (OpenAI-compatible gateway)

| Parameter | Default | Purpose |
|---|---|---|
| `LLM_API_KEY` | `""` | gateway key; empty ⇒ providers return `None`, LLM features off |
| `LLM_BASE_URL` | `https://api.proxyapi.ru/openai/v1` | text gateway base URL |
| `LLM_MODEL` | `""` | text model; empty ⇒ LLM unavailable |
| `LLM_TIMEOUT` | `30.0` | LLM request timeout, s |
| `LLM_VISION_MODEL` | `""` | vision model; falls back to `LLM_MODEL` |
| `LLM_IMAGE_MODEL` | `""` | image model (no fallback); empty ⇒ image generation via this gateway off |
| `LLM_IMAGE_BASE_URL` | `""` | separate base URL for images; `""` ⇒ reuse `LLM_BASE_URL` |
| `LLM_IMAGE_QUALITY` | `""` | `gpt-image*` quality (`low/medium/high`); `""` ⇒ omitted |

### AITunnel (priority image provider)

| Parameter | Default | Purpose |
|---|---|---|
| `AITUNNEL_API_KEY` | `""` | when set — image generation goes through AITunnel (Gemini) instead of `LLM_IMAGE_*` |
| `AITUNNEL_IMAGE_MODEL` | `gemini-3.1-flash-lite-image` | AITunnel model |
| `AITUNNEL_IMAGE_BASE_URL` | `https://api.aitunnel.ru/v1` | AITunnel base URL |

## Outbound HTTP

| Parameter | Default | Purpose |
|---|---|---|
| `HTTP_TIMEOUT` | `10.0` | HTTP client timeout, s |
| `HTTP_MAX_RETRIES` | `2` | retry count (total attempts = retries + 1) |
| `HTTP_BACKOFF_BASE` | `0.5` | exponential backoff base (4 s cap) |
| `PROXY_URL` | `""` | proxy for the `ozon` profile; `""` ⇒ direct |

## Redis

| Parameter | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis address (also the Taskiq broker) |
| `REDIS_MAX_CONNECTIONS` | `10` | pool size |
| `REDIS_SOCKET_TIMEOUT` | `5.0` | socket timeout, s |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `5.0` | connect timeout, s |
| `REDIS_RETRY_ON_TIMEOUT` | `False` | client retries on timeouts |

Redis memory is not configured here but in `backend/config/redis.conf`
(`maxmemory 512mb`, `maxmemory-policy volatile-ttl`).

## Jobs

| Parameter | Default | Purpose |
|---|---|---|
| `JOBS_MODE` | `inline` | `inline` — jobs run synchronously in the handler (dev); `taskiq` — via the worker. Taskiq mode enables job-only stash writes (documents, settlement report) and starts the `JobPoller` |
| `JOBS_POLL_INTERVAL` | `2.0` | active-jobs polling interval, s |

## Price parsing (Playwright) and Ozon CDP

| Parameter | Default | Purpose |
|---|---|---|
| `PRICE_ENABLED` | `True` | enables page-render price escalation (Playwright) |
| `PRICE_HEADLESS` | `False` | WB anti-detect requires headed mode |
| `PRICE_TIMEOUT` | `45.0` | browser scene timeout, s |
| `PROXY_ROTATE_URL` | `""` | browser proxy-rotation URL (optional) |
| `OPTIMAL_PRICE_UNDERCUT_PCT` | `3.0` | how much optimal price sits below the rival's, % |
| `OZON_CDP_URL` | `http://127.0.0.1:9336` | address of the real Edge browser for Ozon (CDP) |

## Caps (limits)

| Parameter | Default | Purpose |
|---|---|---|
| `REVIEWS_CAP` | `50` | max reviews per fetch |
| `NICHE_ITEM_CAP` | `30` | max niche items per marketplace |
| `LEGAL_CARD_CAP` | `10` | max SKUs/links per audit run |
| `LEGAL_DOCUMENT_CAP` | `5` | max documents per audit run |
| `LEGAL_DOCUMENT_MAX_BYTES` | `10 MiB` | byte cap per document (checked before and after download) |
| `FINANCE_REPORT_MAX_BYTES` | `10 MiB` | byte cap per settlement report |

Caps outside settings: `PHOTO_MAX_BYTES = 5 MiB` (`bot/photos.py`),
`MAX_TEXT_LEN = 200_000` / `MAX_ROWS = 5_000` (core/documents),
`REPORT_LIMIT = 4000` chars "message vs file" (`bot/renderers.py`).

## How parameters change

Any default change or new parameter — edit `src/core/settings.py` and
this table in the same PR.
