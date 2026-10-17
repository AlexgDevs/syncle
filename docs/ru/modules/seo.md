# Модуль content (SEO)

Генерация SEO-текста карточки (название, описание, преимущества,
ключевые слова) для WB и Ozon. В модуле также живёт vision-хелпер,
распознающий товар по фото.

## Границы

- **Делает:** промпт → LLM → JSON → валидация `SeoText` → кламп под
  лимиты маркетплейса; vision-описание товара по фото.
- **Не делает:** не парсит маркетплейсы (analytics), не рисует
  инфографику (infographics), не хранит ничего в Redis (stash пишет
  бот).

## Публичный API

Фабрика: `get_seo_service() -> SeoService` (lru_cache).

| Метод | Назначение |
|---|---|
| `async generate(request: SeoRequest, *, on_progress) -> SeoText` | генерация SEO-текста; прогресс `generating_seo` |
| `describe_product(llm, images, hint) -> SeoAttributes` | vision: фото + подсказка → название/категория/бренд/фичи |

Задача: `seo_text` (SEO_JOB_TYPE), handler `seo_generate_job`,
ретраи 1; `register_content_jobs()`. Payload схемы `extra="ignore"`:
бот дописывает delivery-метаданные и `photo_file_ids`.

## Схемы

- `SeoRequest` — вход: `description` (обязательно), `marketplace`,
  опционально advantages/keywords/vision-атрибуты.
- `SeoText` — выход: title, description, bullets, keywords (кламп
  после парсинга).
- `SeoAttributes` — vision: name, category, brand, key_features (≤ 3).
- `SeoLimits` + `SEO_LIMITS`: WB — title 60, description 1000,
  bullets 5×150, keywords 10×50; OZON — title 100, description 1500,
  те же капы bullets/keywords.

## Зависимости

- core: `llm` (`get_llm_provider()`, vision через `images=`,
  `extract_json_object`).
- analytics: только enum `Marketplace` / `MARKETPLACE_TITLES`.
- http/stash/redis: нет.

## Кейсы

**Генерация** (`seo_text`): промпт (типизированный запрос + лимиты
маркетплейса) → LLM → `extract_json_object` → `SeoText.model_validate`
→ кламп (никогда не отклоняет, только урезает) → при ошибке валидации
— 1 repair-ретрай со списком ошибок → иначе `SeoGenerationError`.
Прогресс: `generating_seo`.

**Vision-атрибуты**: фото (≤ 3, до `PHOTO_MAX_BYTES`) + подсказка →
vision LLM → `SeoAttributes`; при неудаче бот деградирует к генерации
по тексту (SEO_NO_VISION).

## Данные и капы

`MAX_ADVANTAGES = 3`, `MAX_KEY_FEATURES = 3`; LLM: temp 0.6 /
900 tokens (генерация), 0.2 / 300 (vision); описание в промпте — ≤ 2000
символов; `_REPAIR_ATTEMPTS = 1`.

## Ошибки → RU

`SeoGenerationError` → SEO_FAILED; `LLMTimeoutError` /
`LLMRateLimitError` → LLM_TIMEOUT_TEXT / LLM_RATE_LIMIT_TEXT.

## Связанные issues/PR

#25–#27 (SEO-текст), #63 (vision). Сцена бота: `handlers/seo_text.py`;
результат — вход в infographics (stash `seo:{chat_id}`).
