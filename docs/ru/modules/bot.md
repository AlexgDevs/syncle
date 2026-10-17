# Модуль bot (интерфейс)

Первичный интерфейс продукта: Telegram-бот на aiogram. Адаптер между
пользователем и доменными модулями — FSM-сцены, клавиатуры, рендеры,
доставка результатов фоновых задач.

## Границы

- **Делает:** приём ввода (текст/ссылки/фото/документы), FSM-сцены,
  запуск задач (inline/taskiq), опрос статусов и доставку, RU-тексты
  и клавиатуры, маппинг ошибок домена на RU.
- **Не делает:** не содержит доменной логики (всё в модулях); не
  импортирует Redis/LLM напрямую (только через модули и core-порты).

## Структура

| Файл | Роль |
|---|---|
| `main.py` | composition root: logging → Bot → `init_redis()` → JobPoller (taskiq) → polling |
| `middlewares.py` | `UserMiddleware`: резолвит/создаёт User + сессию для сообщений и колбэков |
| `polling.py` | `JobPoller`: опрос `syncle:jobs:active`, прогресс, доставка, cleanup |
| `delivery.py` | `AiogramResultSink` (адаптер `core.results.ResultSink`) |
| `handlers/` | сцены (см. ниже) + `common.py` (require_state, launch_job_or_inline, safe_edit) |
| `keyboards/inline/menu.py` | меню (MAIN_ROWS/MENU_ROWS) и scene-клавиатуры |
| `texts.py` | все RU-тексты + `PROGRESS_STEPS` (EN-код → RU) |
| `renderers.py` | форматирование отчётов (`render_*`), капы сообщений |
| `errors.py` | `describe_error` (исключение → RU), `describe_skip_code`, error-хендлеры |
| `photos.py` | `download_photos` (PHOTO_CAP = 3, PHOTO_MAX_BYTES = 5 MiB) |
| `finance_delivery.py`, `niche_delivery.py` | доставка больших отчётов файлом |

## Сцены

| Сцена | Хендлер | Callback | Флоу |
|---|---|---|---|
| Меню | `menu.py` | `menu:*` | навигация, очистка FSM |
| Экспресс-анализ | `express_analysis.py` | `scene:express` | своя карточка (skip) → карточка конкурента → job `analysis` |
| Глубокий скан | `deep_scan.py` | `scene:deep_scan` | маркетплейс → запрос ≥ 2 символов → своя карточка → job `niche_scan` → сообщение или .md |
| SEO-текст | `seo_text.py` | `scene:seo` | маркетплейс → описание + ≤ 3 фото → преимущества (skip) → vision → job `seo_text` → stash seo → результат с кнопкой инфографики |
| Отзывы | `reviews.py` | `scene:reviews` | свой источник → конкурент (skip) → тональность → выборка (пагинация 10/стр) → job `reviews_analysis` |
| Инфографика | `infographics.py` | `scene:infographics` | требует stash SEO → стиль → бриф ≥ 5 → ≤ 3 фото (3-е — старт) → stash brief → job `infographics_render` → фото |
| Юр. карточка | `legal.py` | `scene:legal:card` | ссылка → job `legal_card_scan` (правила, без LLM) или inline |
| Юр. аудит | `legal.py` | `scene:legal:audit` | источники ≤ 10 → текст → документы ≤ 5 (10 MiB) → stash legaldocs → job `legal_scan` |
| Фин. калькулятор | `finance.py` | `scene:finance:calc` | 4 числовых шага → calc() (всегда inline) → what-if кнопки |
| Фин. отчёт | `finance.py` | `scene:finance:report` | документ (10 MiB) → stash finreport → job `finance_report` |

Общие guard'ы: `require_state()` (устаревшие кнопки), `safe_edit()`
(edit → fallback answer), `BACK_TO_MENU` очищает FSM.
`launch_job_or_inline()`: отправка задачи только при `JOBS_MODE=taskiq`
(иначе — inline-фолбэк в хендлере).

## Доставка (ResultSink)

- **Текст:** редактирует status-сообщение («message is not modified»
  игнорируется), иначе новое сообщение.
- **Файл:** `send_document` при отрендеренном тексте > `REPORT_LIMIT =
  4000` символов (сначала edit с пометкой «отчёт файлом», затем
  .md-attach); ≤ 4000 — обычное сообщение.
- **Фото:** удаляет текстовый status, `send_photo` с caption
  (инфографика).

## Polling

`JobPoller(interval=JOBS_POLL_INTERVAL)`: читает active-SET; для
каждого job_type свой рендер-доставка (if-chain в `_deliver_result`):
`analysis`, `niche_scan`, `seo_text` (+stash),
`infographics_render` (фото), `reviews_analysis`, `legal_card_scan`,
`legal_scan`, `finance_report`. Прогресс: `PROGRESS_STEPS[step]`
(дедуп per job). `FAILED` → специальные тексты (FIN_REPORT_EMPTY,
INFO_FAILED) или `JOB_FAILED`; cleanup удаляет hash и active-id.
Запускается только при `JOBS_MODE=taskiq`.

## Ошибки

`describe_error(exc)`: цепочка isinstance по `SyncleError`-дереву
всех модулей + LLM-исключения → RU-текст; фолбэк `GENERIC_ERROR`.
`setup_error_handlers`: `SyncleError` → сообщение; прочие → traceback
в лог + `GENERIC_ERROR`. Пользователь никогда не видит EN/traceback.

## Зависимости

Все доменные модули (через публичные сервисы), core (redis, jobs,
settings, stash-функции), aiogram. `UserMiddleware` — modules/user.

## Связанные issues/PR

Сцены: #1–#14 (экспресс), #18–#19 (ниша), #26/#63 (SEO), #28–#32
(отзывы), #53–#61 (legal), #45–#52 (finance), #62 (инфографика);
UX-кнопка меню — PR #74.
