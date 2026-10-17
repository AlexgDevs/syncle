# Модуль infographics

Генерация инфографики-постера товара из SEO-текста через image-LLM
(Gemini/AITunnel, фолбэк OpenAI-совместимый шлюз).

## Границы

- **Делает:** плашки текста из SeoText, структурирование клиентского
  брифа (text-LLM), сборка арт-директорского промпта, рендер PNG.
- **Не делает:** не генерирует SEO (content), не хранит данные в
  сервисе (stash пишет бот, читает job), не знает про Telegram.

## Публичный API

Фабрика: `get_infographics_service() -> InfographicsService`
(lru_cache; шарит image- и text-провайдеры).

| Метод | Назначение |
|---|---|
| `build_plates(request) -> PlateSet` | чистая сборка текстовых плашек (без сети) |
| `async render(request, *, photos, brief, on_progress) -> bytes` | полный пайплайн → PNG |

Задача: `infographics_render` (INFOGRAPHICS_JOB_TYPE), ретраи 1;
payload `{chat_id, variant, status_message_id}` (лёгкий);
`register_infographics_jobs()`.

## Схемы и enum

`StyleVariant` (minimalism | premium | bright_sale), `PlateKind`
(header | feature | keywords), `Plate` (1..80 символов), `PlateSet`,
`InfographicRequest` (seo: SeoText + variant; `extra="ignore"`),
`RenderedArtwork` (variant, mime image/png, base64), `BriefOverrides`
(product_name ≤ 200, product_information ≤ 1500, key_features ≤ 5,
optional_text ≤ 200, brand_style ≤ 500, target_audience ≤ 300).

## Зависимости

- core: `llm` (text — структурирование брифа; image —
  `get_image_provider()`: AITunnel при `AITUNNEL_API_KEY`, иначе
  `LLM_IMAGE_*`), `stash`: `load_stashed_entry` (SEO + фото,
  `seo:{chat_id}`), `load_brief` (`infobrief:{chat_id}`).
- content: `SeoText` (единственная связь с SEO).
- Ассет: `backend/assets/prompts/poster-gemini.txt` (шаблон
  арт-директора, ~21k символов).

## Кейсы

**Рендер** (`infographics_render`): payload → stash SEO (просрочка →
`InfographicsRenderError` «stashed SEO expired») → опционально бриф
(свежие фото брифа важнее фото эпохи SEO) → `render()`:
1. `build_plates`: заголовок → header, ≤ N bullets → features,
   keywords → полосой; description не используется.
2. При брифе — text-LLM структурирует его в `BriefOverrides`
   (фолбэк: сырой бриф, обрезанный до 1500 символов).
3. Заполнение 7 плейсхолдеров шаблона → image edits call (фото как
   image input или текстовая композиция) → PNG 1024×1024.
Прогресс: `structuring_brief` → `composing_prompt` →
`rendering_image`.

**Вход из бота:** кнопка на результате SEO (stash обязателен) →
вариант стиля → бриф ≥ 5 символов → до 3 фото (3-е авто-старт).

## Данные и капы

`MAX_PLATES = 6`, `IMAGE_SIZE = "1024x1024"`;
`PLATE_LIMITS`: minimalism 4 плашки / 3 фичи / 60 символов;
premium 5/4/70; bright_sale 6/5/80.
Реестр моделей (`models.py`): ручной список image-моделей с ценами в
рублях и пометками совместимости; `model_note()` для подсказки в
интерфейсе. Дефолты шлюза: `DEFAULT_IMAGE_MODEL = "gpt-image-1"`,
`DEFAULT_IMAGE_QUALITY = "medium"`.

## Ошибки → RU

`InfographicsError` → INFO_FAILED; `InfographicsRenderError`
(просроченный stash, нет модели, пустой ответ) → INFO_FAILED /
INFO_STASH_EXPIRED с подсказкой перегенерировать SEO.

## Связанные issues/PR

#62–#63 (M7-v5, стили, бриф, фото). Сцена бота:
`handlers/infographics.py`; доставка фото — `polling.py`
(deliver_photo).
