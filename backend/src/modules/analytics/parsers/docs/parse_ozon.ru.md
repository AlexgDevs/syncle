# Парсинг Ozon

- Статус: актуально
- Дата: 2026-10-07
- Затрагивает: #39 (поиск ниши), #43/#44 (глубокий скан), ADR-004 (транспорт)
- Код: `parsers/ozon.py`, `parsers/ozon_search.py`, `parsers/cdp.py`,
  `parsers/constants.py`
- Транспорт: исключительно реальный браузер по CDP (Ozon отклоняет
  обычные HTTP-клиенты)

## Назначение

Ozon-парсинг приводит ссылку/артикул к `CompetitorCard`, `Review`,
`NicheItem` через контракты `parsers/base.py`. В отличие от WB, здесь нет
«обычного HTTP» уровня: каждый запрос выполняется внутри запущенного вручную
Edge (см. скрипты `scripts/start_cdp_edge.sh`, `scripts/start_cdp_edge_linux.sh`).

## Нормализация ввода

- `parsers/source.py: parse_source`: цифры — артикул (без URL), остальное —
  ссылка (при отсутствии схемы добавляется `https://`).
- Ссылка товара распознаётся регулярками `OZON_PRODUCT_ID`
  (`/product/<slug>-<id>/` и короткий `/product/<id>/`) и `OZON_CATALOG_ID`
  (`/catalog/<id>/`); нераспознанная ссылка → `CardParseError`.
- **UX-правило:** чисто цифровой источник трактуется как WB, поэтому для
  Ozon нужна полная ссылка.

## Транспорт — CDP-сессия

- `parsers/cdp.py: CdpJsonClient` — GET выполняется `fetch(...,
  credentials: "include")` **внутри страницы** браузера, подключённого по
  `connect_over_cdp` к `OZON_CDP_URL` (по умолчанию `http://127.0.0.1:9336`).
- Требования к браузеру (иначе — HTTP 403 или недоступность):
  - обычное окно, **не headless**: headless UA Ozon отвечает 403;
  - отдельный `--user-data-dir`: с основного профиля порт отладки не
    поднимается; профиль хранит куки Ozon (холодный профиль первое время
    может отдавать 403);
  - запуск через `scripts/start_cdp_edge.sh` (Windows/Git Bash) или
    `scripts/start_cdp_edge_linux.sh` (Linux, ищет Edge/Chromium/Chrome).
- Одна страница на origin + `asyncio.Lock` сериализуют запросы; после
  ошибок сессия пересоздаётся (`_teardown`).

## Источники данных

### 1. Карточка — composer page API

- `GET OZON_PAGE_API + quote(path)` → JSON со словарём `widgetStates`.
- Виджеты: `webProductHeading` (заголовок), `webPrice` (цена),
  `webReviewProductScore` (рейтинг/число отзывов), `webBrand` (бренд),
  `breadCrumbs` (категория — первый элемент хлебных крошек);
  SEO-описание — из `seo.meta[name=description]`.
- Ключи виджетов имеют вид `<widget>-<id>-…`; совпадение требует точного
  имени (чтобы `webPrice` не матчился с `webPriceDecreased…`).

### 2. Отзывы — entrypoint API

- `GET OZON_REVIEWS_API + quote(path)`, path =
  `/product/<id>/reviews/pdp-part?layout_container=reviewshelfpaginator&layout_page_index=<n>&tab=reviews`.
- Маленькие серверные страницы; пагинация останавливается, когда страница
  пуста, достигнут заявленный `paging.total`, или включился `REVIEWS_CAP`
  (лимит 50 серверных страниц).
- 404 на первой странице → `CardNotFoundError`; битые записи пропускаются.

### 3. Поиск ниши — composer page API (issue #39)

- `GET OZON_PAGE_API + quote("/search?text=…&from_global=true&page=N")`
  внутри браузерной страницы; карточки лежат в видах `tileGridDesktop-*`
  (8 товаров на страницу), обход до лимита или `_MAX_PAGES = 10`.
- Поля товара: `sku` → `ozon_product_url(sku)`, цена из `mainState.priceV2`,
  название из `textDS id=name`, бренд из `labelListV2 automationId=
  tile-list-labels` (маскирующие бейджи отфильтровываются), рейтинг/отзывы
  из `tile-list-rating`.

## Ошибки и деградация

| Исключение | Условие | Поведение бота |
|---|---|---|
| `CardNotFoundError` | HTTP 404 на карточке/отзывах | «Товар не найден…» |
| `CardParseError` | не-JSON, битый payload, HTTP ≠ 200/404, **бот-челлендж** (`fab_chlg` / `incidentId`+`challengeURL`) | «Не удалось получить карточку…» |
| `NicheSearchError` | поиск ниши ответил ≠ 200 или не содержит данных | RU-текст `NICHE_SEARCH_FAILED` |
| `OzonBrowserError` | CDP-эндпоинт недоступен / сбой сессии | «Браузерный модуль Ozon временно недоступен…» |

## Настройки

`OZON_CDP_URL` (endpoint), `REVIEWS_CAP`, `NICHE_ITEM_CAP`.

## Проверка

- `bash scripts/start_cdp_edge.sh` (или `_linux.sh`) — поднять CDP-браузер;
  скрипт идемпотентен и сам проверяет endpoint.
- `smoke_e2e.py` — Ozon-нога: 30 товаров, цены, бэнды, LLM-инсайты,
  рендер отчёта; `smoke_card.py` проверяет WB (Ozon-карточка — вручную по
  ссылке `/product/<id>/`).
