# Module bot (interface)

The product's primary interface: a Telegram bot on aiogram. An adapter
between the user and the domain modules — FSM scenes, keyboards,
rendering, and background-job delivery.

## Boundaries

- **Does:** input handling (text/links/photos/documents), FSM scenes,
  job launching (inline/taskiq), status polling and delivery, RU texts
  and keyboards, mapping domain errors to RU.
- **Does not:** hold domain logic (it lives in modules); import
  Redis/LLM directly (only via modules and core ports).

## Structure

| File | Role |
|---|---|
| `main.py` | composition root: logging → Bot → `init_redis()` → JobPoller (taskiq) → polling |
| `middlewares.py` | `UserMiddleware`: resolves/creates the User + session for messages and callbacks |
| `polling.py` | `JobPoller`: polls `syncle:jobs:active`, progress, delivery, cleanup |
| `delivery.py` | `AiogramResultSink` (adapter of `core.results.ResultSink`) |
| `handlers/` | scenes (below) + `common.py` (require_state, launch_job_or_inline, safe_edit) |
| `keyboards/inline/menu.py` | menus (MAIN_ROWS/MENU_ROWS) and scene keyboards |
| `texts.py` | all RU texts + `PROGRESS_STEPS` (EN code → RU) |
| `renderers.py` | report formatting (`render_*`), message caps |
| `errors.py` | `describe_error` (exception → RU), `describe_skip_code`, error handlers |
| `photos.py` | `download_photos` (PHOTO_CAP = 3, PHOTO_MAX_BYTES = 5 MiB) |
| `finance_delivery.py`, `niche_delivery.py` | large-report file delivery |

## Scenes

| Scene | Handler | Callback | Flow |
|---|---|---|---|
| Menu | `menu.py` | `menu:*` | navigation, FSM reset |
| Express analysis | `express_analysis.py` | `scene:express` | own card (skip) → rival card → job `analysis` |
| Deep niche scan | `deep_scan.py` | `scene:deep_scan` | marketplace → query ≥ 2 chars → own card → job `niche_scan` → message or .md |
| SEO text | `seo_text.py` | `scene:seo` | marketplace → description + ≤ 3 photos → advantages (skip) → vision → job `seo_text` → stash seo → result with the infographics button |
| Reviews | `reviews.py` | `scene:reviews` | own source → rival (skip) → tone → selection (10/page pagination) → job `reviews_analysis` |
| Infographics | `infographics.py` | `scene:infographics` | requires stashed SEO → style → brief ≥ 5 → ≤ 3 photos (3rd auto-start) → stash brief → job `infographics_render` → photo |
| Legal card | `legal.py` | `scene:legal:card` | link → job `legal_card_scan` (rules, no LLM) or inline |
| Legal audit | `legal.py` | `scene:legal:audit` | sources ≤ 10 → text → documents ≤ 5 (10 MiB) → stash legaldocs → job `legal_scan` |
| Finance calculator | `finance.py` | `scene:finance:calc` | 4 numeric steps → calc() (always inline) → what-if buttons |
| Finance report | `finance.py` | `scene:finance:report` | document (10 MiB) → stash finreport → job `finance_report` |

Shared guards: `require_state()` (stale-button protection),
`safe_edit()` (edit → fallback answer), `BACK_TO_MENU` clears the FSM.
`launch_job_or_inline()`: submits only under `JOBS_MODE=taskiq`
(otherwise the handler runs the inline fallback).

## Delivery (ResultSink)

- **Text:** edits the status message ("message is not modified" is
  ignored), else a new message.
- **File:** `send_document` when the rendered text exceeds
  `REPORT_LIMIT = 4000` chars (first an edit noting the file, then the
  .md attach); ≤ 4000 — a plain message.
- **Photo:** deletes the text status, `send_photo` with a caption
  (infographics).

## Polling

`JobPoller(interval=JOBS_POLL_INTERVAL)`: reads the active SET; each
job_type has its own render-delivery (an if-chain in
`_deliver_result`): `analysis`, `niche_scan`, `seo_text` (+stash),
`infographics_render` (photo), `reviews_analysis`, `legal_card_scan`,
`legal_scan`, `finance_report`. Progress: `PROGRESS_STEPS[step]`
(deduped per job). `FAILED` → special texts (FIN_REPORT_EMPTY,
INFO_FAILED) or `JOB_FAILED`; cleanup removes the hash and active id.
Started only under `JOBS_MODE=taskiq`.

## Errors

`describe_error(exc)`: an isinstance chain over every module's
`SyncleError` tree plus LLM exceptions → RU text; fallback
`GENERIC_ERROR`. `setup_error_handlers`: `SyncleError` → message;
others → traceback logged + `GENERIC_ERROR`. Users never see EN text or
tracebacks.

## Dependencies

All domain modules (via public services), core (redis, jobs, settings,
stash functions), aiogram. `UserMiddleware` — modules/user.

## Related issues/PRs

Scenes: #1–#14 (express), #18–#19 (niche), #26/#63 (SEO), #28–#32
(reviews), #53–#61 (legal), #45–#52 (finance), #62 (infographics);
menu UX — PR #74.
