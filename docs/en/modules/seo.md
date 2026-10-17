# Module content (SEO)

Generation of card SEO text (title, description, bullets, keywords)
for WB and Ozon. The module also hosts the vision helper that
recognizes a product from photos.

## Boundaries

- **Does:** prompt → LLM → JSON → `SeoText` validation → clamp to
  marketplace limits; vision product description from photos.
- **Does not:** parse marketplaces (analytics), render infographics
  (infographics), store anything in Redis (the bot writes the stash).

## Public API

Factory: `get_seo_service() -> SeoService` (lru_cache).

| Method | Purpose |
|---|---|
| `async generate(request: SeoRequest, *, on_progress) -> SeoText` | SEO text generation; progress `generating_seo` |
| `describe_product(llm, images, hint) -> SeoAttributes` | vision: photos + hint → name/category/brand/features |

Job: `seo_text` (SEO_JOB_TYPE), handler `seo_generate_job`, 1 retry;
`register_content_jobs()`. Schemas use `extra="ignore"`: the bot
appends delivery metadata and `photo_file_ids`.

## Schemas

- `SeoRequest` — input: `description` (required), `marketplace`,
  optional advantages/keywords/vision attributes.
- `SeoText` — output: title, description, bullets, keywords (clamped
  post-parse).
- `SeoAttributes` — vision: name, category, brand, key_features (≤ 3).
- `SeoLimits` + `SEO_LIMITS`: WB — title 60, description 1000,
  bullets 5×150, keywords 10×50; OZON — title 100, description 1500,
  same bullet/keyword caps.

## Dependencies

- core: `llm` (`get_llm_provider()`, vision via `images=`,
  `extract_json_object`).
- analytics: `Marketplace` / `MARKETPLACE_TITLES` enums only.
- http/stash/redis: none.

## Use cases

**Generation** (`seo_text`): prompt (typed request + marketplace
limits) → LLM → `extract_json_object` → `SeoText.model_validate` →
clamp (never rejects, only trims) → on validation errors one repair
retry listing them → else `SeoGenerationError`. Progress:
`generating_seo`.

**Vision attributes**: photos (≤ 3, under `PHOTO_MAX_BYTES`) + hint →
vision LLM → `SeoAttributes`; on failure the bot degrades to
text-only generation (SEO_NO_VISION).

## Data and caps

`MAX_ADVANTAGES = 3`, `MAX_KEY_FEATURES = 3`; LLM: temp 0.6 / 900
tokens (generation), 0.2 / 300 (vision); prompt descriptions clipped
to 2000 chars; `_REPAIR_ATTEMPTS = 1`.

## Errors → RU

`SeoGenerationError` → SEO_FAILED; `LLMTimeoutError` /
`LLMRateLimitError` → LLM_TIMEOUT_TEXT / LLM_RATE_LIMIT_TEXT.

## Related issues/PRs

#25–#27 (SEO text), #63 (vision). Bot scene: `handlers/seo_text.py`;
the result feeds infographics (stash `seo:{chat_id}`).
