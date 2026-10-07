# Парсинг Wildberries

- Статус: актуально
- Дата: 2026-10-07
- Затрагивает: #21 (цена), #39 (поиск ниши), #43/#44 (глубокий скан), ADR-004
- Код: `parsers/wb.py`, `parsers/wb_price.py`, `parsers/wb_search.py`,
  `parsers/browser.py`, `parsers/constants.py`
- Транспорт: обычный HTTP (`httpx`) + Playwright-браузер (уровень 3)

## Назначение

Слой парсинга приводит пользовательский ввод (ссылка или артикул) к
моделям домена (`CompetitorCard`, `Review`, `NicheItem`). Публичный контракт —
протоколы `parsers/base.py`: `CardParser`, `ReviewsSource`, `CardPriceSource`,
`NicheSearcher`. Все уровни эскалации парсинга цены описаны в ADR-004;
этот документ фиксирует, как устроен WB-парсинг целиком.

## Нормализация ввода

- `parsers/source.py: parse_source` — цифровой ввод это артикул WB
  (URL нет), всё остальное нормализуется добавлением `https://`.
- Артикул извлекается регуляркой `NM_FROM_URL` (`/catalog/<nm>/`).
- **UX-правило:** чисто цифровой источник всегда трактуется как WB;
  Ozon требует полной ссылки (об этом сообщается в промпте).

## Источники данных

### 1. Карточка — `card.json`

- URL вида `…/vol<vol>/part<part>/<nm>/info/ru/card.json`, где
  `vol = nm // 100_000`, `part = nm // 1000`.
- Хосты из `WB_CARD_HOSTS`: первый — гео-CDN
  `mow-basket-cdn-{basket:02d}.geobasket.ru`; легаси
  `basket-{basket:02d}.wbbasket.ru` пробуется **только если CDN не ответил
  вовсе** (сеть/гео). Живой 404 от CDN означает «товара нет» — дополнительный
  запрос к легаси давал бы лишь шум и латентность.
- Шард (basket) неизвестен: кандидаты — эвристика `BASKET_GUESSES`
  (vol → basket) + кэш успешных `vol → basket` + обход 1..46.
- Поля: `imt_name`, `description`, `selling.brand_name`, `subj_name`;
  рейтинг и отзывы берутся из feedbacks (ниже), не из card.json.

### 2. Рейтинг и отзывы — `feedbacks2.wb.ru`

- `GET /feedbacks/v2/<imt_id>` даёт `valuation` (рейтинг) и `feedbackCount`.
- Отзывы приходят одним батчем: query-пагинация (`take/skip/page`)
  эндпоинтом игнорируется, поэтому `REVIEWS_CAP` применяется на клиенте.
- Разбор «best effort»: битые записи пропускаются, отсутствующие поля →
  `None`; сетевой сбой или не-JSON → `CardParseError`.

### 3. Цена — уровень 3 (ADR-004)

- Обычный HTTP бесполезен: карточка отдаёт JS-челлендж (498), API-хосты —
  403. Рабочий источник — отрендеренная страница `/catalog/<nm>/detail.aspx`.
- Источники по приоритету: `<title>` («… купить за 4 907 ₽ …»), затем первая
  сумма в purchase-панели тела страницы (обрезается по маркерам рекомендаций
  «Хит продаж», «Рекомендуем» и т.д., чтобы не взять чужую цену).
- Опрос раз в секунду до `PRICE_TIMEOUT`; «ничего не найдено» в title →
  ранний выход. Любая ошибка → `price = None` («недоступна»), парсинг
  карточки не падает.
- Опциональная ротация IP: один повтор через `PROXY_ROTATE_URL`, если заданы
  оба прокси-настройки.

### 4. Поиск ниши — перехват сети (issue #39)

- Прямой `search.wb.ru` отвечает 403 → открывается реальная страница
  `/catalog/0/search.aspx?search=…`, и из сетевого лога перехватывается
  ответ `__internal/u-search/...`, который SPA делает сам.
- Из `products` собираются `NicheItem`: цены в копейках (`sizes[0].price.product`),
  `reviewRating`, `feedbacks`, ссылка строится `wb_product_url(nm)`.
- Гейт: `PRICE_ENABLED=false` отключает и поиск (`NicheSearchError`).

## Транспорт и антибот

- `parsers/browser.py: wb_browser_session` — общий для цены и поиска
  Playwright-сессии: свежий профиль на каждый запуск, `locale=ru-RU`,
  `timezone=Europe/Moscow`, фиксированный Chrome-UA, скрытый
  `navigator.webdriver`, опциональный прокси из `PROXY_URL`.
- `PRICE_HEADLESS` по умолчанию `false`: headless детектится WB-челленджем
  (см. ADR-004, пробы).
- Playwright не установлен → `BrowserUnavailable` (не ошибка домена).

## Ошибки и деградация

| Исключение | Условие | Поведение бота |
|---|---|---|
| `CardNotFoundError` | артикул не найден (живой 404 CDN) | «Товар не найден…» |
| `CardParseError` | нет ответа от всех хостов, битый payload | «Не удалось получить карточку…» |
| `NicheSearchError` | сбой/гейт поиска ниши | RU-текст `NICHE_SEARCH_FAILED` |
| `BrowserUnavailable` → `None`/`NicheSearchError` | нет Playwright | цена «недоступна» / ошибка поиска |

## Настройки

`PRICE_ENABLED`, `PRICE_HEADLESS`, `PRICE_TIMEOUT`, `PROXY_URL`,
`PROXY_ROTATE_URL`, `REVIEWS_CAP`, `NICHE_ITEM_CAP`.

## Проверка

- `smoke_card.py`: карточка + отзывы + `CardNotFoundError` на несуществующем
  артикуле.
- `smoke_e2e.py`: WB-нога скана ниши (30 товаров, цены, бэнды, инсайты).
