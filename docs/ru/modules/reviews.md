# Модуль reviews

Анализ отзывов конкурентов/собственных: LLM сводит жалобы и
преимущества в тегированные группы с пунктами для копирования.

## Границы

- **Делает:** сбор отзывов (через analytics-парсеры), LLM-анализ в
  выбранной тональности, нормализацию и бюджетирование вывода.
- **Не делает:** не парсит маркетплейсы самостоятельно, не хранит
  данные, не работает с Redis.

## Публичный API

Фабрика: `get_reviews_service() -> ReviewAnalysisService` (lru_cache).

| Метод | Назначение |
|---|---|
| `async analyze(request: ReviewAnalysisRequest, *, on_progress) -> ReviewReport` | LLM-анализ; прогресс `analyzing_reviews` |
| `async fetch_reviews(source) -> list[Review]` | сбор отзывов (адаптер поверх analytics) |

Задача: `reviews_analysis` (REVIEWS_JOB_TYPE), ретраи 1;
`register_reviews_jobs()`.

## Схемы

- `Tone` — neutral | soft | harsh.
- `ReviewSource` — role (own|rival) + описание + список отзывов.
- `ReviewAnalysisRequest` — tone + 1–2 источника (`extra="ignore"`:
  бот дописывает delivery-метаданные).
- `Finding` — RU-тег (`#Слово_Слово`, строгий regex `TAG_PATTERN`) +
  1..N пунктов; `ReviewReport` — tone + findings.

## Зависимости

- core: `llm`, `jobs`.
- analytics: `Review`, `get_analytics_service().fetch_reviews`;
  тайповые ошибки парсинга проходят насквозь (`CardNotFoundError`,
  `OzonBrowserError`, `UnsupportedMarketplaceError`), `CardParseError`
  маппится на `ReviewsFetchError`.

## Кейсы

1. Бот собирает источники (свой и/или конкурент: ссылка → fetch, или
   свободный текст ≥ 10 символов), тональность, выборку отзывов из
   fetched-списка → `ReviewAnalysisRequest` + job.
2. LLM-вывод валидируется (pydantic + regex тегов); 1 repair-ретрай с
   ошибками; затем `ReviewAnalysisError`.
3. `_normalize()`: дедупликация тегов без учёта регистра, слияние и
   обрезка пунктов, бюджеты — `MAX_FINDINGS` × `MAX_POINTS_PER_TAG`.

## Данные и капы

`MAX_SOURCES = 2`, `MAX_FINDINGS = 8` тегов, `MAX_POINTS_PER_TAG = 3`,
`MAX_POINT_LEN = 80` (под лимит CopyTextButton 256);
LLM: temp 0.4 / 900 tokens, обрезка отзыва до 400 символов в промпте;
`_REPAIR_ATTEMPTS = 1`.

## Ошибки → RU

`ReviewAnalysisError` → REVIEWS_FAILED, `ReviewsFetchError` →
REVIEWS_FETCH_FAILED; проходящие ошибки analytics обрабатываются их же
RU-текстами.

## Связанные issues/PR

#28–#32 (сцена репутации, теги, бюджеты). Сцена бота:
`handlers/reviews.py`.
