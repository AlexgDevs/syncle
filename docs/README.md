# Документация Syncle

Документация проекта: стандарты разработки, архитектурные паттерны,
практические выводы и документация по модулям.

## Структура

```
docs/
├── adr/                      Архитектурные решения (ADR)
├── ru/                       Источник истины (русский)
│   ├── development/          Принципы, стандарты, паттерны, выводы
│   ├── modules/              Документация модулей
│   └── configuration.md      Параметры .env
└── en/                       Английские переводы
```

## Порядок чтения

1. [development/principles.md](ru/development/principles.md) — ключевые
   концепции (слои, модульность, владение) и принципы (SOLID, DRY, KISS,
   YAGNI).
2. [development/standards.md](ru/development/standards.md) — как пишем
   код, как коммитим, что проверяем перед сдачей.
3. [development/patterns.md](ru/development/patterns.md) — реализация
   принципов механизмами проекта (порты, задачи, stash, ошибки).
4. [development/lessons.md](ru/development/lessons.md) — краткие
   практические выводы; читать перед нетривиальными правками.
5. [configuration.md](ru/configuration.md) — все параметры `.env`.
6. Модули (`ru/modules/`) — по мере наполнения:
   [core.md](ru/modules/core.md) ✚, [analytics.md](ru/modules/analytics.md) ✚,
   [seo.md](ru/modules/seo.md) ✚, [reviews.md](ru/modules/reviews.md) ✚;
   legal, finance, infographics, bot, user — в работе.

## Договорённости

- **Русский — source of truth.** EN-версии являются переводами и обновляются
  синхронно с RU.
- **Docstring в коде** описывает контракт (сигнатуры, капы, guard'ы);
  **документация здесь** описывает систему (зачем, кейсы, зависимости).
  Доки ссылаются на код; код не дублирует доки.
- **ADR** (`adr/`) — для решений с альтернативами, которые нельзя молча
  поменять. Всё остальное — в development/ или docs модуля.
- Локальный черновик `ARCHITECTURE.md` в корне репозитория не коммитится
  (через `.git/info/exclude`); его содержимое перенесено в
  [development/patterns.md](ru/development/patterns.md).

## Как дополнить

Новый модуль или нетривиальная фича → обнови соответствующий
`modules/<name>.md` (или создай по шаблону из patterns.md, раздел
«Шаблон документа модуля») в том же PR, что и код.
