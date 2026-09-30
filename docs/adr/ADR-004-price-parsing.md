# ADR-004: Источник цены Wildberries

- Статус: принято
- Дата: 2026-09-30
- Затрагивает: #21 (спайк цены), K04/K06, `optimal_price`

## Контекст

Сценарий «экспресс-анализ» обещает цену карточки и расчёт оптимальной цены,
но цена не парсилась: `CompetitorCard.price` всегда `None`, `optimal_price`
всегда `None` (TODO P07/K04). Нужен рабочий источник цены.

## Результаты проб (2026-09-30)

| Источник | Результат |
|---|---|
| `basket-*.wbbasket.ru/.../info/ru/card.json` | 200, но цены в JSON нет (`selling` = бренд, `data` = chrt_ids) |
| `vol.json` / `vol-all-options.json` / `options.json` | 404 |
| `card.wb.ru/cards/v2|v6/detail` | 403 (пусто, сервер `wbaas`), с куками и Origin/Referer тоже |
| `search.wb.ru/...` | 403 |
| HTML `wildberries.ru` обычным HTTP | 498 — JS-антибот `__wbaas/challenges/antibot` (browser-check.js + behavior-tracker + challenge-solver, site-key) |
| `curl_cffi` `impersonate=chrome/safari/firefox` | 498 — TLS-имперсонации недостаточно, требует выполнения JS |
| Playwright, `headless=True` | челлендж не проходит (детект headless), `create-token` 498 |
| **Playwright, `headless=False`** | **челлендж проходит автоматически за ~4-5 с, карточка рендерится, цена доступна** |

Цена на отрендеренной странице: в `<title>` («…покупать за 4 907 ₽…») и в DOM
(4 808 ₽ с WB Кошельком / 4 907 ₽ / старая зачёркнутая). Прокси при объёмах
проекта (единицы запросов в анализ) не потребовался — тест прошёл с обычного IP.

## Решение

1. Уровень парсинга цены — **Playwright** (`headless=False`, ru-локаль,
   скрытый `navigator.webdriver`), источник цены — `<title>` страницы
   `/catalog/{nm}/detail.aspx`; парсинг через `parse_title_price`.
2. Изоляция за портом `CardPriceSource` (`parsers/base.py`); реализация —
   `WbPriceSource` (`parsers/wb_price.py`). Любая ошибка → `price = None`
   («недоступна»), парсинг карточки не падает.
3. Опциональный прокси: `PROXY_URL` (launch proxy) + `PROXY_ROTATE_URL`
   (HTTP-эндпоинт смены IP, один повтор при неудаче) — задел на случай
   блокировки IP при росте объёмов.
4. Настройки: `PRICE_ENABLED`, `PRICE_HEADLESS`, `PRICE_TIMEOUT`,
   `OPTIMAL_PRICE_UNDERCUT_PCT` (default 3).
5. `optimal_price = price_конкурента × (1 − pct/100)`, округление до копеек
   (ROUND_HALF_UP); если цены нет — `None`.

## Альтернативы (отклонены)

- `curl_cffi` с impersonate — не проходит JS-челлендж (498).
- Прямые API (`card.wb.ru`, `search.wb.ru`) — 403 на уровне сервера.
- Сторонние API (BHAPI и подобные) — платная внешняя зависимость, out of scope.
- Покупка прокси сразу — по пробам не нужна; подключается точечно через
  настройки, без изменения кода.

## Последствия

- Зависимости: `playwright` + chromium (~200 МБ), уже в `pyproject`.
- `headless=False` требует дисплея: на Windows-хосте ок; на Linux-сервере —
  Xvfb либо переключить `PRICE_HEADLESS=true` и проверить повторно.
- Латентность: +5-10 с на карточку (запуск браузера + челлендж); при
  фоновых задачах (#8/#9) это закрывается Taskiq-очередью.
- Риск: WB может ужесточить антибот → правки локализованы в
  `WbPriceSource`, запасной путь — прокси-ротация, финальный фоллбэк —
  `price=None`.
