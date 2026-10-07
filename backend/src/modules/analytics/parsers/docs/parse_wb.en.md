# Wildberries Parsing

- Status: active
- Date: 2026-10-07
- Relates to: #21 (price), #39 (niche search), #43/#44 (deep scan), ADR-004
- Code: `parsers/wb.py`, `parsers/wb_price.py`, `parsers/wb_search.py`,
  `parsers/browser.py`, `parsers/constants.py`
- Transport: plain HTTP (`httpx`) plus a Playwright browser (level 3)

## Purpose

The parsing layer turns user input (link or article) into domain models
(`CompetitorCard`, `Review`, `NicheItem`). The public contract is the set of
protocols in `parsers/base.py`: `CardParser`, `ReviewsSource`,
`CardPriceSource`, `NicheSearcher`. The price escalation levels are recorded
in ADR-004; this document describes the WB parsing pipeline as a whole.

## Input normalization

- `parsers/source.py: parse_source` — a digit-only input is a WB article
  (no URL); anything else is normalized by prepending `https://`.
- The article is extracted from the URL by `NM_FROM_URL` (`/catalog/<nm>/`).
- **UX rule:** a purely numeric source is always treated as WB; Ozon
  requires a full link (stated in the prompt).

## Data sources

### 1. Product card — `card.json`

- URL pattern `…/vol<vol>/part<part>/<nm>/info/ru/card.json`, where
  `vol = nm // 100_000`, `part = nm // 1000`.
- Hosts come from `WB_CARD_HOSTS`: first the geo CDN
  `mow-basket-cdn-{basket:02d}.geobasket.ru`; the legacy
  `basket-{basket:02d}.wbbasket.ru` is tried **only when the CDN does not
  answer at all** (network/geo failure). A live 404 from the CDN means the
  product does not exist — an extra legacy probe would only add noise and
  latency.
- The shard (basket) is unknown: candidates are the `BASKET_GUESSES`
  heuristic (vol → basket), a cache of successful `vol → basket` mappings,
  and a scan over 1..46.
- Fields: `imt_name`, `description`, `selling.brand_name`, `subj_name`;
  rating and reviews come from the feedbacks endpoint (below), not card.json.

### 2. Rating and reviews — `feedbacks2.wb.ru`

- `GET /feedbacks/v2/<imt_id>` provides `valuation` (rating) and
  `feedbackCount`.
- Reviews arrive as a single batch: query pagination (`take/skip/page`) is
  ignored by the endpoint, so `REVIEWS_CAP` is applied client-side.
- Parsing is best effort: malformed entries are skipped, missing fields
  become `None`; a network failure or a non-JSON body raises
  `CardParseError`.

### 3. Price — level 3 (ADR-004)

- Plain HTTP is a dead end: the card serves a JS challenge (498) and API
  hosts answer 403. The only working source is the rendered page
  `/catalog/<nm>/detail.aspx`.
- Sources in priority order: `<title>` ("... buy for 4,907 ₽ ..."), then the
  first amount in the purchase panel of the page body (truncated at
  recommendation markers such as "Хит продаж", "Рекомендуем", so an
  unrelated product price is never taken).
- Polled once per second until `PRICE_TIMEOUT`; "not found" in the title
  triggers an early exit. Any failure degrades to `price = None`
  ("unavailable") — card parsing never fails because of the price.
- Optional IP rotation: a single retry through `PROXY_ROTATE_URL` when both
  proxy settings are configured.

### 4. Niche search — network interception (issue #39)

- A direct `search.wb.ru` request answers 403, so a real page
  `/catalog/0/search.aspx?search=…` is opened and the SPA's own
  `__internal/u-search/...` response is captured from the network log.
- `NicheItem`s are built from `products`: prices are in kopecks
  (`sizes[0].price.product`), plus `reviewRating`, `feedbacks`; the link is
  built with `wb_product_url(nm)`.
- Gate: `PRICE_ENABLED=false` also disables search (`NicheSearchError`).

## Transport and anti-bot

- `parsers/browser.py: wb_browser_session` — a shared Playwright session for
  both the price source and the search: a fresh profile per run,
  `locale=ru-RU`, `timezone=Europe/Moscow`, a fixed Chrome UA, a hidden
  `navigator.webdriver`, and an optional proxy from `PROXY_URL`.
- `PRICE_HEADLESS` defaults to `false`: headless is detected by the WB
  challenge (see ADR-004, probes).
- Playwright not installed → `BrowserUnavailable` (not a domain error).

## Errors and degradation

| Exception | Condition | Bot behavior |
|---|---|---|
| `CardNotFoundError` | article missing (live 404 from CDN) | "Product not found…" |
| `CardParseError` | no answer from any host, broken payload | "Failed to fetch the card…" |
| `NicheSearchError` | niche search failure/gate | RU text `NICHE_SEARCH_FAILED` |
| `BrowserUnavailable` → `None`/`NicheSearchError` | Playwright missing | price "unavailable" / search error |

## Settings

`PRICE_ENABLED`, `PRICE_HEADLESS`, `PRICE_TIMEOUT`, `PROXY_URL`,
`PROXY_ROTATE_URL`, `REVIEWS_CAP`, `NICHE_ITEM_CAP`.

## Verification

- `smoke_card.py`: card plus reviews plus `CardNotFoundError` for a
  non-existent article.
- `smoke_e2e.py`: the WB leg of the niche scan (30 items, prices, bands,
  insights).
