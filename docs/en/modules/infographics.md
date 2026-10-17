# Module infographics

Product poster generation from SEO text via an image LLM
(Gemini/AITunnel, OpenAI-compatible gateway fallback).

## Boundaries

- **Does:** text plates from SeoText, structuring the customer brief
  (text LLM), art-director prompt assembly, PNG rendering.
- **Does not:** generate SEO (content), store data inside the service
  (the bot writes the stash, the job reads it), know about Telegram.

## Public API

Factory: `get_infographics_service() -> InfographicsService`
(lru_cache; shares the image and text providers).

| Method | Purpose |
|---|---|
| `build_plates(request) -> PlateSet` | pure text-plate assembly (no network) |
| `async render(request, *, photos, brief, on_progress) -> bytes` | full pipeline → PNG |

Job: `infographics_render` (INFOGRAPHICS_JOB_TYPE), 1 retry; payload
`{chat_id, variant, status_message_id}` (light);
`register_infographics_jobs()`.

## Schemas and enums

`StyleVariant` (minimalism | premium | bright_sale), `PlateKind`
(header | feature | keywords), `Plate` (1..80 chars), `PlateSet`,
`InfographicRequest` (seo: SeoText + variant; `extra="ignore"`),
`RenderedArtwork` (variant, mime image/png, base64), `BriefOverrides`
(product_name ≤ 200, product_information ≤ 1500, key_features ≤ 5,
optional_text ≤ 200, brand_style ≤ 500, target_audience ≤ 300).

## Dependencies

- core: `llm` (text — brief structuring; image —
  `get_image_provider()`: AITunnel when `AITUNNEL_API_KEY` is set,
  else `LLM_IMAGE_*`), `stash`: `load_stashed_entry` (SEO + photos,
  `seo:{chat_id}`), `load_brief` (`infobrief:{chat_id}`).
- content: `SeoText` (the only coupling with SEO).
- Asset: `backend/assets/prompts/poster-gemini.txt` (art-director
  template, ~21k chars).

## Use cases

**Render** (`infographics_render`): payload → stashed SEO (expired →
`InfographicsRenderError` "stashed SEO expired") → optional brief
(fresh brief photos win over SEO-era photos) → `render()`:
1. `build_plates`: title → header, ≤ N bullets → features, keywords →
   a strip; the description is not used.
2. With a brief — a text LLM structures it into `BriefOverrides`
   (fallback: raw brief clipped to 1500 chars).
3. Fill 7 template placeholders → image edits call (photos as image
   input or a text-only composition) → 1024×1024 PNG.
Progress: `structuring_brief` → `composing_prompt` →
`rendering_image`.

**Bot entry:** a button on the SEO result (stash required) → style
variant → brief ≥ 5 chars → up to 3 photos (the 3rd auto-starts).

## Data and caps

`MAX_PLATES = 6`, `IMAGE_SIZE = "1024x1024"`;
`PLATE_LIMITS`: minimalism 4 plates / 3 features / 60 chars;
premium 5/4/70; bright_sale 6/5/80.
Model registry (`models.py`): a manual list of image models with RUB
prices and compatibility notes; `model_note()` for interface hints.
Gateway defaults: `DEFAULT_IMAGE_MODEL = "gpt-image-1"`,
`DEFAULT_IMAGE_QUALITY = "medium"`.

## Errors → RU

`InfographicsError` → INFO_FAILED; `InfographicsRenderError`
(expired stash, missing model, empty response) → INFO_FAILED /
INFO_STASH_EXPIRED with a hint to regenerate the SEO text.

## Related issues/PRs

#62–#63 (M7-v5, styles, brief, photos). Bot scene:
`handlers/infographics.py`; photo delivery — `polling.py`
(deliver_photo).
