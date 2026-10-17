# Module reviews

Review analysis for your own and rival products: an LLM condenses
complaints and strengths into tagged groups with copy-ready points.

## Boundaries

- **Does:** review collection (via analytics parsers), LLM analysis
  in a chosen tone, normalization and output budgeting.
- **Does not:** parse marketplaces itself, store data, touch Redis.

## Public API

Factory: `get_reviews_service() -> ReviewAnalysisService` (lru_cache).

| Method | Purpose |
|---|---|
| `async analyze(request: ReviewAnalysisRequest, *, on_progress) -> ReviewReport` | LLM analysis; progress `analyzing_reviews` |
| `async fetch_reviews(source) -> list[Review]` | review collection (analytics adapter) |

Job: `reviews_analysis` (REVIEWS_JOB_TYPE), 1 retry;
`register_reviews_jobs()`.

## Schemas

- `Tone` — neutral | soft | harsh.
- `ReviewSource` — role (own|rival) + description + reviews list.
- `ReviewAnalysisRequest` — tone + 1–2 sources (`extra="ignore"`: the
  bot appends delivery metadata).
- `Finding` — RU tag (`#Word_Word`, strict `TAG_PATTERN` regex) +
  1..N points; `ReviewReport` — tone + findings.

## Dependencies

- core: `llm`, `jobs`.
- analytics: `Review`, `get_analytics_service().fetch_reviews`;
  typed parsing errors pass through (`CardNotFoundError`,
  `OzonBrowserError`, `UnsupportedMarketplaceError`);
  `CardParseError` maps to `ReviewsFetchError`.

## Use cases

1. The bot collects sources (own and/or rival: link → fetch, or free
   text ≥ 10 chars), tone, and a selection of fetched reviews →
   `ReviewAnalysisRequest` + job.
2. LLM output is validated (pydantic + tag regex); one repair retry
   with errors; then `ReviewAnalysisError`.
3. `_normalize()`: case-insensitive tag dedupe, point merge/cut,
   budgets — `MAX_FINDINGS` × `MAX_POINTS_PER_TAG`.

## Data and caps

`MAX_SOURCES = 2`, `MAX_FINDINGS = 8` tags, `MAX_POINTS_PER_TAG = 3`,
`MAX_POINT_LEN = 80` (under Telegram's 256-char CopyTextButton limit);
LLM: temp 0.4 / 900 tokens, reviews clipped to 400 chars in prompts;
`_REPAIR_ATTEMPTS = 1`.

## Errors → RU

`ReviewAnalysisError` → REVIEWS_FAILED, `ReviewsFetchError` →
REVIEWS_FETCH_FAILED; passing analytics errors use their own RU texts.

## Related issues/PRs

#28–#32 (reputation scene, tags, budgets). Bot scene:
`handlers/reviews.py`.
