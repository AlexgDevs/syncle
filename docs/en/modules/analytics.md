# Module analytics

Marketplace card parsing (WB/Ozon), rival comparison, and deep niche
scans. The core of the product: SEO, legal, and reviews take their data
from here.

## Boundaries

- **Does:** parsing cards and reviews, niche search, niche
  aggregation, SEO-key diff, positioning verdicts, LLM analysis of
  content weaknesses and niche insights, optimal-price heuristic.
- **Does not:** generate SEO texts (content), scan for risks (legal),
  touch files/Redis.

## Public API

Factory: `get_analytics_service() -> ExpressAnalysisService`
(lru_cache; shares parsers and the CDP session).

| Method | Purpose |
|---|---|
| `async compare_cards(own_source, rival_source, on_progress) -> AnalysisReport` | express analysis: two cards → report |
| `async fetch_card(source) -> CompetitorCard` | single card fetch (used by legal) |
| `async fetch_reviews(source) -> list[Review]` | card reviews (used by reviews) |
| `async scan_niche(marketplace, query, own_source, on_progress) -> NicheReport` | niche search + aggregates + LLM insights |

Jobs: `analysis` (ANALYSIS_JOB_TYPE), `niche_scan`
(NICHE_SCAN_JOB_TYPE); 1 retry each; `register_analytics_jobs()`.

Pure functions (no network): `build_niche_stats`, `parse_insights`,
`parse_weaknesses`, `missed_seo_keys` / `extract_keys` (SEO diff),
`positioning_recommendations` (price/keywords/rating axes),
`parse_json_list` (shared tolerant JSON decoder).

## Schemas

`CompetitorCard` (normalized card), `Review`, `NicheItem`,
`NicheStats` (prices/brands/words/ratings), `NicheReport`,
`AnalysisReport` (rival/own, missed SEO keys, weaknesses,
positioning, `optimal_price`), `PositioningInsight`; aggregates
`BrandShare`, `WordCount`, `PriceBand`, `FeedbackBand`.
`Marketplace` (wb/ozon), `Axis`, `Stance`, `MARKETPLACE_TITLES`.

## Dependencies

- core: `http` (profiles `basket`, `feedbacks`), `llm`
  (`get_llm_provider()`), settings (`OZON_CDP_URL`, `PRICE_*`,
  `PROXY_URL`, `PROXY_ROTATE_URL`, `OPTIMAL_PRICE_UNDERCUT_PCT`,
  `NICHE_ITEM_CAP`, `REVIEWS_CAP`).
- Browsers: Playwright Chromium (WB, `parsers/browser.py`, anti-detect,
  headed), real Edge over CDP (Ozon, `parsers/cdp.py`).
- stash: none. DB: none.

## Use cases

**Express analysis** (`analysis`): parse own+rival concurrently →
`optimal_price` (undercut `OPTIMAL_PRICE_UNDERCUT_PCT` below the
rival's price) → deterministic SEO-key diff (`MAX_MISSED_KEYS = 12`)
and positioning → LLM content weaknesses (≤ 5; degrades to empty on
`LLMError`) → `AnalysisReport`. Progress: `parsing_cards` →
`analyzing_content`.

**Deep niche scan** (`niche_scan`): one search per marketplace (no
per-item fetches) → `NicheStats` aggregation (up to
`NICHE_ITEM_CAP = 30` items) → optional own card (parse failure
degrades to a niche-only analysis) → LLM insights (≤ 6; degrade to
empty) → `NicheReport`. Progress: `searching_niche` →
`analyzing_niche`.

**Single card/reviews** — reused by legal and reviews.

## Data and caps

- `NICHE_ITEM_CAP = 30`, `REVIEWS_CAP = 50` (settings); Ozon reviews —
  ≤ 50 pages, Ozon search — ≤ 10 pages (8 items/page).
- SEO diff: `MAX_MISSED_KEYS = 12`; weaknesses ≤ 5; insights ≤ 6;
  descriptions clamped to 3000 chars in prompts.
- LLM: comparison — temp 0.4 / 800 tokens; niche — 0.4 / 700.
- Price: WB escalation via Playwright (level 3: `<title>`, then the
  rendered body); browser unavailable — degrade to `None`.

## Errors → RU (bot/errors.py)

`CardParseError` → PARSE_FAILED; `CardNotFoundError` →
CARD_NOT_FOUND; `UnsupportedMarketplaceError` →
UNSUPPORTED_MARKETPLACE; `OzonBrowserError` →
OZON_BROWSER_UNAVAILABLE; `NicheSearchError` → NICHE_SEARCH_FAILED.

## Related issues/PRs

#1–#14 (parsers, comparison), #18–#19 (niche), #24 (positioning),
ADR-004 (price parsing); parser docs:
`backend/src/modules/analytics/parsers/docs/`.
