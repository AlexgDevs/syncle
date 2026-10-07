# Ozon Parsing

- Status: active
- Date: 2026-10-07
- Relates to: #39 (niche search), #43/#44 (deep scan), ADR-004 (transport)
- Code: `parsers/ozon.py`, `parsers/ozon_search.py`, `parsers/cdp.py`,
  `parsers/constants.py`
- Transport: exclusively a real browser over CDP (Ozon rejects plain
  HTTP clients)

## Purpose

The Ozon pipeline turns a link/article into `CompetitorCard`, `Review`,
`NicheItem` through the contracts in `parsers/base.py`. Unlike WB, there is
no "plain HTTP" tier: every request runs inside a manually started Edge
(see `scripts/start_cdp_edge.sh` and `scripts/start_cdp_edge_linux.sh`).

## Input normalization

- `parsers/source.py: parse_source`: digits are an article (no URL); the
  rest is a link (the `https://` scheme is added when missing).
- Product links are recognized by `OZON_PRODUCT_ID` (`/product/<slug>-<id>/`
  and the short `/product/<id>/`) and `OZON_CATALOG_ID` (`/catalog/<id>/`);
  an unrecognized link raises `CardParseError`.
- **UX rule:** a purely numeric source is treated as WB, so Ozon requires a
  full link.

## Transport — CDP session

- `parsers/cdp.py: CdpJsonClient` — the GET is executed as
  `fetch(..., credentials: "include")` **inside a browser page** connected
  over `connect_over_cdp` to `OZON_CDP_URL` (default
  `http://127.0.0.1:9336`).
- Browser requirements (otherwise HTTP 403 or unavailability):
  - a regular, **non-headless** window: Ozon answers 403 to headless UAs;
  - a dedicated `--user-data-dir`: the debugging port cannot be enabled on
    the default profile; the profile keeps the Ozon cookies warm (a cold
    profile may answer 403 for a while);
  - launch via `scripts/start_cdp_edge.sh` (Windows/Git Bash) or
    `scripts/start_cdp_edge_linux.sh` (Linux; probes Edge/Chromium/Chrome).
- One page per origin plus an `asyncio.Lock` serializes requests; the
  session is rebuilt after failures (`_teardown`).

## Data sources

### 1. Product card — composer page API

- `GET OZON_PAGE_API + quote(path)` → JSON with a `widgetStates` map.
- Widgets: `webProductHeading` (title), `webPrice` (price),
  `webReviewProductScore` (rating/review count), `webBrand` (brand),
  `breadCrumbs` (category — the first breadcrumb); the SEO description
  comes from `seo.meta[name=description]`.
- Widget keys look like `<widget>-<id>-…`; matching requires the exact
  widget name (so `webPrice` never matches `webPriceDecreased…`).

### 2. Reviews — entrypoint API

- `GET OZON_REVIEWS_API + quote(path)`, path =
  `/product/<id>/reviews/pdp-part?layout_container=reviewshelfpaginator&layout_page_index=<n>&tab=reviews`.
- Small server-driven pages; pagination stops when a page is empty, the
  reported `paging.total` is reached, or `REVIEWS_CAP` kicks in (hard cap
  of 50 server pages).
- HTTP 404 on the first page → `CardNotFoundError`; malformed entries are
  skipped.

### 3. Niche search — composer page API (issue #39)

- `GET OZON_PAGE_API + quote("/search?text=…&from_global=true&page=N")`
  from inside the browser page; products live in the `tileGridDesktop-*`
  widgets (8 items per page), walked until the limit or
  `_MAX_PAGES = 10`.
- Item fields: `sku` → `ozon_product_url(sku)`, price from
  `mainState.priceV2`, title from `textDS id=name`, brand from
  `labelListV2 automationId=tile-list-labels` (masking badges are
  filtered out), rating/reviews from `tile-list-rating`.

## Errors and degradation

| Exception | Condition | Bot behavior |
|---|---|---|
| `CardNotFoundError` | HTTP 404 on card/reviews | "Product not found…" |
| `CardParseError` | non-JSON, broken payload, HTTP ≠ 200/404, **bot challenge** (`fab_chlg` / `incidentId`+`challengeURL`) | "Failed to fetch the card…" |
| `NicheSearchError` | search answered ≠ 200 or carried no data | RU text `NICHE_SEARCH_FAILED` |
| `OzonBrowserError` | CDP endpoint down / session failure | "Ozon browser module is temporarily unavailable…" |

## Settings

`OZON_CDP_URL` (endpoint), `REVIEWS_CAP`, `NICHE_ITEM_CAP`.

## Verification

- `bash scripts/start_cdp_edge.sh` (or `_linux.sh`) — start the CDP
  browser; the script is idempotent and probes the endpoint itself.
- `smoke_e2e.py` — the Ozon leg: 30 items, prices, bands, LLM insights,
  report rendering; `smoke_card.py` covers WB (check an Ozon card manually
  via a `/product/<id>/` link).
