# Модуль analytics

Разбор карточек маркетплейсов (WB/Ozon), сравнение с конкурентом и
глубокий скан ниши. Ядро продукта: отсюда данные берут SEO, legal,
reviews.

## Границы

- **Делает:** парсинг карточек и отзывов, поиск по нише, агрегацию
  ниши, дифф SEO-ключей, позиционные вердикты, LLM-разбор слабостей
  контента и инсайтов ниши, эвристику optimal price.
- **Не делает:** не генерирует SEO-тексты (content), не сканирует на
  риски (legal), не работает с файлами/Redis.

## Публичный API

Фабрика: `get_analytics_service() -> ExpressAnalysisService`
(lru_cache; шарит парсеры и CDP-сессию).

| Метод | Назначение |
|---|---|
| `async compare_cards(own_source, rival_source, on_progress) -> AnalysisReport` | экспресс-анализ: две карточки → отчёт |
| `async fetch_card(source) -> CompetitorCard` | одиночный разбор карточки (использует legal) |
| `async fetch_reviews(source) -> list[Review]` | отзывы карточки (использует reviews) |
| `async scan_niche(marketplace, query, own_source, on_progress) -> NicheReport` | поиск ниши + агрегаты + LLM-инсайты |

Задачи: `analysis` (ANALYSIS_JOB_TYPE), `niche_scan`
(NICHE_SCAN_JOB_TYPE); ретраи 1; регистрация `register_analytics_jobs()`.

Чистые функции (без сети): `build_niche_stats`, `parse_insights`,
`parse_weaknesses`, `missed_seo_keys` / `extract_keys` (SEO-дифф),
`positioning_recommendations` (3 оси: цена/ключи/рейтинг),
`parse_json_list` (общий толерантный JSON-decoder).

## Схемы

`CompetitorCard` (нормализованная карточка: source/title/description/
brand/category/price/rating/feedbacks_count), `Review`, `NicheItem`,
`NicheStats` (цены/бренды/слова/рейтинги), `NicheReport`,
`AnalysisReport` (rival/own, missed SEO keys, weaknesses,
positioning, `optimal_price`), `PositioningInsight`; агрегаты
`BrandShare`, `WordCount`, `PriceBand`, `FeedbackBand`.
`Marketplace` (wb/ozon), `Axis`, `Stance`, `MARKETPLACE_TITLES`.

## Зависимости

- core: `http` (профили `basket`, `feedbacks`), `llm`
  (`get_llm_provider()`), settings (`OZON_CDP_URL`, `PRICE_*`,
  `PROXY_URL`, `PROXY_ROTATE_URL`, `OPTIMAL_PRICE_UNDERCUT_PCT`,
  `NICHE_ITEM_CAP`, `REVIEWS_CAP`).
- Браузеры: Playwright-Chromium (WB, `parsers/browser.py`,
  антидетект, headed), реальный Edge через CDP (Ozon, `parsers/cdp.py`).
- stash: нет. БД: нет.

## Кейсы

**Экспресс-анализ** (`analysis`): парс own+rival конкурентно →
`optimal_price` (undercut `OPTIMAL_PRICE_UNDERCUT_PCT` от цены
конкурента) → детерминированный дифф SEO-ключей (лимит
`MAX_MISSED_KEYS = 12`) и позиционирование → LLM-слабости контента
(≤ 5 пунктов; при `LLMError` — деградация до пустого списка) →
`AnalysisReport`. Прогресс: `parsing_cards` → `analyzing_content`.

**Глубокий скан** (`niche_scan`): один поиск на маркетплейс (без
выборки по карточкам) → агрегация `NicheStats` (до
`NICHE_ITEM_CAP = 30` позиций) → опционально своя карточка (ошибка
парсинга деградирует к анализу без неё) → LLM-инсайты (≤ 6; деградация
до пустого) → `NicheReport`. Прогресс: `searching_niche` →
`analyzing_niche`.

**Одиночная карточка/отзывы** — переиспользуются legal и reviews.

## Данные и капы

- `NICHE_ITEM_CAP = 30`, `REVIEWS_CAP = 50` (settings), Ozon-отзывы —
  ≤ 50 страниц, Ozon-поиск — ≤ 10 страниц (8 позиций/страница).
- SEO-дифф: `MAX_MISSED_KEYS = 12`; weaknesses ≤ 5; insights ≤ 6;
  описание в промпте клампится до 3000 символов.
- LLM: сравнение — temp 0.4 / 800 tokens; ниша — 0.4 / 700.
- Цена: WB-эскалация через Playwright (level 3: `<title>`, затем
  отрендеренное тело); недоступность браузера — деградация к `None`.

## Ошибки → RU (bot/errors.py)

`CardParseError` → PARSE_FAILED; `CardNotFoundError` →
CARD_NOT_FOUND; `UnsupportedMarketplaceError` →
UNSUPPORTED_MARKETPLACE; `OzonBrowserError` →
OZON_BROWSER_UNAVAILABLE; `NicheSearchError` → NICHE_SEARCH_FAILED.

## Связанные issues/PR

#1–#14 (парсеры, сравнение), #18–#19 (ниша), #24 (позиционирование),
ADR-004 (price parsing); доки парсеров:
`backend/src/modules/analytics/parsers/docs/`.
