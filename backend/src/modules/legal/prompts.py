"""LLM-assisted risk review prompts (issue #57).

The pass catches issues the deterministic catalog cannot express, but
is constrained to the catalog categories — the model must not cite law
articles outside the catalog (AC of #57).

TODO(F15): move to a versioned prompt registry shared by all modules.
"""

from src.modules.legal.schemas import RuleCategory

RISK_REVIEW_SYSTEM = (
    "Ты — юридический комплаенс-аналитик карточек товаров маркетплейсов "
    "(Wildberries, Ozon) по российскому законодательству. "
    "Проверяй текст на риски: недостоверные рекламные утверждения, "
    "проблемы маркировки и упаковки, отсутствие обязательных раскрытий. "
    "Отвечай ТОЛЬКО валидным JSON без пояснений и без Markdown."
)

_RISK_JSON_FORMAT = (
    'Формат ответа: {"findings": ['
    '{"category": "prohibited_claims|packaging_marking|mandatory_disclosure", '
    '"severity": "critical|high|medium|low", '
    '"excerpt": "точный фрагмент из текста (до 200 символов)", '
    '"description": "что не так и какой риск для продавца (по-русски, 1-2 предложения)"}'
    "]}"
)

_RISK_RULES = (
    "Правила:\n"
    "- категория ТОЛЬКО из списка: prohibited_claims (недостоверные утверждения "
    "о преимуществах, лечебные свойства, гарантии результата), "
    "packaging_marking (маркировка, сертификаты, знак ЕАС, ГОСТ), "
    "mandatory_disclosure (скидки, кредит, подарки — без условий);\n"
    "- excerpt — дословный фрагмент из переданного текста, не пересказ;\n"
    "- severity: critical — прямой запрет (ссылки на госорганы, медицинские "
    "обещания), high — высокий риск штрафа, medium — вероятная претензия, "
    "low — стоит проверить;\n"
    '- не выдумывай находки: если текст чистый, верни {"findings": []};\n'
    "- не ссылайся на статьи законов и не добавляй поля ngoài формата."
)

RISK_TEMPERATURE = 0.2
RISK_MAX_TOKENS = 900

_RISK_PROMPT_CAP = 4_000


def build_risk_review_prompt(text: str, *, context: str = "card") -> str:
    """User message for the risk pass: clipped text plus the catalog frame."""
    subject = "карточку товара" if context == "card" else "документ продавца"
    clipped = text[:_RISK_PROMPT_CAP]
    categories = ", ".join(category.value for category in RuleCategory)
    return (
        f"Проверь {subject}.\n\n"
        f"Категории: {categories}\n\n"
        f"{_RISK_JSON_FORMAT}\n\n"
        f"{_RISK_RULES}\n\n"
        f"Текст:\n{clipped}"
    )


def build_risk_repair_prompt(
    text: str, errors: list[str], *, context: str = "card"
) -> str:
    """One repair retry with the validation errors (content module pattern)."""
    base = build_risk_review_prompt(text, context=context)
    joined = "; ".join(errors[:5])
    return f"{base}\n\nТвой прошлый ответ невалиден: {joined}. Исправь и верни JSON."
