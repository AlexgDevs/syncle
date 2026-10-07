import re

NM_FROM_URL = re.compile(r"/catalog/(\d+)/")

WB_ORIGIN = "https://www.wildberries.ru"
OZON_ORIGIN = "https://www.ozon.ru"
OZON_PAGE_API = OZON_ORIGIN + "/api/composer-api.bx/page/json/v2?url="
OZON_REVIEWS_API = OZON_ORIGIN + "/api/entrypoint-api.bx/page/json/v2?url="


def wb_product_url(nm: int) -> str:
    return f"{WB_ORIGIN}/catalog/{nm}/detail.aspx"


def ozon_product_url(sku: int) -> str:
    return f"{OZON_ORIGIN}/product/{sku}/"


# Ozon product slugs always end with the numeric article: both
# /product/<slug>-<id>/ and the short /product/<id>/ match.
OZON_PRODUCT_ID = re.compile(r"^/product/(?:[^/?#]*-)?(\d+)/?$")
OZON_CATALOG_ID = re.compile(r"^/catalog/(\d+)/?$")

BASKET_GUESSES: list[tuple[int, int]] = [
    (143, 1),
    (287, 2),
    (431, 3),
    (719, 4),
    (1007, 5),
    (1061, 6),
    (1115, 7),
    (1169, 8),
    (1313, 9),
    (1601, 10),
    (1655, 11),
    (1919, 12),
    (2045, 13),
    (2189, 14),
    (2405, 15),
    (2621, 16),
    (2837, 17),
    (3053, 18),
    (3269, 19),
    (3485, 20),
    (3701, 21),
    (3917, 22),
    (4133, 23),
    (4349, 24),
    (4565, 25),
    (4877, 26),
    (5189, 27),
    (5501, 28),
    (5813, 29),
    (6125, 30),
    (6437, 31),
    (6749, 32),
    (7061, 33),
    (7373, 34),
    (7685, 35),
    (7997, 36),
    (8309, 37),
    (8741, 38),
    (9173, 39),
    (9605, 40),
    (10373, 41),
    (11141, 42),
    (11909, 43),
    (12677, 44),
    (13445, 45),
    (14213, 46),
]

# WB moved card.json from basket-XX.wbbasket.ru (now HTML 404 on every
# shard for every article) to a geo CDN. The first host is authoritative;
# the legacy host is only tried when the CDN does not answer at all
# (network/geo failure), so a live 404 from the CDN means the card does
# not exist and the legacy probe would only add noise.
WB_CARD_HOSTS: list[str] = [
    "https://mow-basket-cdn-{basket:02d}.geobasket.ru",
    "https://basket-{basket:02d}.wbbasket.ru",
]
