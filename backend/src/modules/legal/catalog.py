"""Initial RU compliance rules catalog (issue #54, draft for review).

Every entry carries a source reference and an example violation. The
catalog is data only — behavior lives in the engine. Sources point at
the general framework (2300-ФЗ, ПП РФ №1236, 184-ФЗ, ТР ТС); the seller
must verify specifics with their own compliance officer.
"""

from src.modules.legal.schemas import Rule, RuleCategory, Severity

_R001 = Rule(
    id="R001",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Превосходная оценка товара («лучший», «самый лучший») запрещена: "
        "недостоверные сведения о преимуществах товара."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236 (перечень недостоверных сведений)",
    example="«Лучшая зарядка на рынке», «Самый лучший смартфон»",
    keywords=["лучший", "лучшая", "лучшие", "лучшее", "лучшего", "лучшей"],
    patterns=[r"сам\w*\s+лучш"],
)

_R002 = Rule(
    id="R002",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Утверждения о первенстве («№1», «лидер рынка», «занимает первое место») "
        "относятся к недостоверным сведениям о преимуществах."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«№1 среди продавцов», «Лидер рынка 2025»",
    patterns=[r"(?:№|n)\s*1\b"],
    keywords=["лидер рынка", "занимает первое место", "первая строчка"],
)

_R003 = Rule(
    id="R003",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Утверждения о самой низкой цене относятся к недостоверным сведениям."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«Самая низкая цена в России», «Дешевле всех»",
    patterns=[r"сам\w*\s+(?:низк\w*\s+цен|дешев\w*)"],
    keywords=["дешевле всех", "лучшая цена в россии"],
)

_R004 = Rule(
    id="R004",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Утверждения об уникальности/отсутствии аналогов — недостоверные сведения."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«Не имеет аналогов в мире», «Единственный на рынке»",
    keywords=["не имеет аналогов", "аналогов нет", "уникальный", "уникальная"],
    patterns=[r"единственн\w*\s+(?:в\s+(?:мире|россий|росси))"],
)

_R005 = Rule(
    id="R005",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.CRITICAL,
    description=(
        "Ссылки на одобрение/рекомендации государственных органов и учреждений "
        "прямо запрещены перечнем."
    ),
    source="ПП РФ №1236, п. 2",
    example="«Рекомендовано Минздравом», «Одобрено санэпиднадзором»",
    keywords=[
        "рекомендовано министерством",
        "рекомендован министерством",
        "одобрено министерством",
        "одобрено минздравом",
        "рекомендовано минздравом",
        "санэпиднадзор рекомендует",
        "разрешено минздравом",
        "одобрено роспотребнадзором",
    ],
)

_R006 = Rule(
    id="R006",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Утверждения о лечебных свойствах недопустимы для товаров, не являющихся "
        "лекарственными средствами."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236; 61-ФЗ «О лекарственных средствах»",
    example="«Лечит простуду», «Терапевтический эффект», «Помогает вылечить»",
    keywords=[
        "лечит",
        "излечивает",
        "вылечить",
        "лечебный эффект",
        "лечебное средство",
        "терапевтический эффект",
        "терапевтическое действие",
    ],
)

_R007 = Rule(
    id="R007",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Утверждения об убивании вирусов/бактерий и противовирусных свойствах "
        "относятся к лечебным свойствам."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«Убивает 99% вирусов», «Противовирусный эффект»",
    keywords=[
        "антибактериальный",
        "бактерицидный",
        "убивает вирусы",
        "убивает вирус",
        "убивает бактерии",
        "противовирусный",
        "от коронавируса",
        "от ковида",
    ],
)

_R008 = Rule(
    id="R008",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description=(
        "Гарантии результата и абсолютные обещания — недостоверные сведения "
        "о свойствах товара."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«100% гарантия результата», «Мгновенный эффект навсегда»",
    patterns=[r"100\s*%\s*гарант"],
    keywords=[
        "гарантированный результат",
        "гарантия результата",
        "мгновенный эффект",
        "навсегда",
        "навечно",
    ],
)

_R009 = Rule(
    id="R009",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.MEDIUM,
    description=(
        "Утверждения об экологической чистоте/безвредности относятся к "
        "недостоверным сведениям о свойствах товара."
    ),
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«Экологически чистый материал», «Абсолютно безопасен»",
    patterns=[r"экологическ\w*\s+чист\w*"],
    keywords=["абсолютно безопасен", "абсолютно безопасна", "безвреден", "безвредна"],
)

_R010 = Rule(
    id="R010",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.HIGH,
    description="Утверждения о защите от излучения/радиации — недостоверные сведения.",
    source="2300-ФЗ, ст. 5; ПП РФ №1236",
    example="«Антирадиационный экран», «Защищает от радиации»",
    keywords=["антирадиационный", "антирадиационная", "от радиации"],
    patterns=[r"защит\w*\s+от\s+(?:излучени|радиаци)"],
)

_R011 = Rule(
    id="R011",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.MEDIUM,
    description=(
        "Формы превосходной оценки («элитный», «первоклассный») относятся "
        "к недостоверным сведениям."
    ),
    source="ПП РФ №1236 (превосходная степень)",
    example="«Элитный дизайн», «Первоклассное качество»",
    keywords=["элитный", "элитная", "первоклассный", "первоклассное"],
)

_R012 = Rule(
    id="R012",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.MEDIUM,
    description=(
        "Гарантии возврата денег сверх прав потребителя формулируются "
        "как недостоверное обещание."
    ),
    source="2300-ФЗ, ст. 5, ст. 18",
    example="«Вернём деньги без вопросов», «Деньги вернём обязательно»",
    keywords=["вернём деньги", "вернем деньги", "деньги вернём", "деньги вернем"],
)

_R013 = Rule(
    id="R013",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.MEDIUM,
    description="Обещания пожизненной/бессрочной гарантии вводят покупателя в заблуждение.",
    source="2300-ФЗ, ст. 5, ст. 190 (закон о гарантиях)",
    example="«Пожизненная гарантия», «Вечная гарантия на изделие»",
    keywords=["пожизненная гарантия", "вечная гарантия", "бессрочная гарантия"],
)

_R014 = Rule(
    id="R014",
    category=RuleCategory.PROHIBITED_CLAIMS,
    severity=Severity.MEDIUM,
    description="Утверждения о происхождении требуют подтверждающих документов.",
    source="ПП РФ №1236 (сведения о стране происхождения)",
    example="«Сделано в России», «Российского производства»",
    patterns=[r"сделан\w*\s+в\s+(?:росси|китае|индии|беларус)"],
    keywords=["российского производства", "российское производство"],
)

_R020 = Rule(
    id="R020",
    category=RuleCategory.MANDATORY_DISCLOSURE,
    severity=Severity.LOW,
    description=(
        "Указание скидки/акции требует основания и сроков действия "
        "(отсутствие условий вводит покупателя в заблуждение)."
    ),
    source="ПП РФ №1662 (правила продажи с указанием скидки); 2300-ФЗ, ст. 10",
    example="«Скидка 50%» без указания периода и основания",
    keywords=["скидка", "скидки", "распродажа", "цена со скидкой"],
    contexts=frozenset({"card"}),
)

_R021 = Rule(
    id="R021",
    category=RuleCategory.MANDATORY_DISCLOSURE,
    severity=Severity.LOW,
    description="Условия рассрочки/кредита/трейд-ин должны раскрываться покупателю.",
    source="2300-ФЗ, ст. 10; 353-ФЗ (потребительский кредит)",
    example="«Кредит за 5 минут» без условий и ставки",
    keywords=["рассрочка", "в кредит", "кредит", "трейд-ин", "трейдин"],
    contexts=frozenset({"card"}),
)

_R022 = Rule(
    id="R022",
    category=RuleCategory.MANDATORY_DISCLOSURE,
    severity=Severity.LOW,
    description=(
        "Обещания бесплатного получения требуют раскрытия условий "
        "(сумма заказа, регион, сроки)."
    ),
    source="2300-ФЗ, ст. 10; Правила продажи (ПП РФ №2463)",
    example="«Бесплатная доставка» без условий",
    keywords=["бесплатная доставка", "бесплатно", "в подарок", "подарок"],
    contexts=frozenset({"card"}),
)

_R030 = Rule(
    id="R030",
    category=RuleCategory.PACKAGING_MARKING,
    severity=Severity.MEDIUM,
    description=(
        "Заявление о соответствии ГОСТ требует подтверждающих документов; "
        "отсутствие основания — риск претензий."
    ),
    source="184-ФЗ «О техническом регулировании», ст. 46",
    example="«Соответствует ГОСТу», «Произведено по ГОСТ»",
    keywords=["по госту", "соответствует гост", "гост р"],
    patterns=[r"\bгост\s+(?:р\s*)?\d"],
)

_R031 = Rule(
    id="R031",
    category=RuleCategory.PACKAGING_MARKING,
    severity=Severity.LOW,
    description=(
        "Упоминание сертификата/декларации соответствия: проверьте реквизиты "
        "и доступность копии документа покупателю."
    ),
    source="184-ФЗ, ст. 28, ст. 29 (документы о соответствии)",
    example="«Есть сертификат соответствия» без реквизитов",
    keywords=["сертификат соответствия", "декларация о соответствии", "сертификат"],
)

_R032 = Rule(
    id="R032",
    category=RuleCategory.PACKAGING_MARKING,
    severity=Severity.LOW,
    description=(
        "«Санитарный сертификат» — устаревшая форма документа; действуют "
        "декларация о соответствии и свидетельство о государственной регистрации."
    ),
    source="Решение Комиссии ТС №299 (отмена санитарных сертификатов)",
    example="«Санитарный сертификат на всю продукцию»",
    keywords=["санитарный сертификат", "санитарные сертификаты"],
)

_R033 = Rule(
    id="R033",
    category=RuleCategory.PACKAGING_MARKING,
    severity=Severity.MEDIUM,
    description=(
        "Знак ЕАС/ЕАЭС на маркировке обязателен только для товаров, "
        "подпадающих под технические регламенты; проверьте применимость."
    ),
    source="Решение Совета ЕЭК №83 (правила маркировки знаком ЕАС)",
    example="«Знак ЕАС на упаковке» у товара вне регламентов",
    keywords=["знак еас", "маркировка еас", "еас сертификат"],
)

_CATALOG: tuple[Rule, ...] = (
    _R001,
    _R002,
    _R003,
    _R004,
    _R005,
    _R006,
    _R007,
    _R008,
    _R009,
    _R010,
    _R011,
    _R012,
    _R013,
    _R014,
    _R020,
    _R021,
    _R022,
    _R030,
    _R031,
    _R032,
    _R033,
)

RU_RULES: tuple[Rule, ...] = _CATALOG

RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in _CATALOG}


def catalog_rules(context: str = "card") -> tuple[Rule, ...]:
    """Rules applicable to a scan context (card / document)."""
    return tuple(rule for rule in _CATALOG if context in rule.contexts)
