# Syncle Documentation

Project documentation: development standards, architectural patterns,
practical lessons, and per-module docs.

## Layout

```
docs/
├── adr/                      Architecture Decision Records
├── ru/                       Source of truth (Russian)
│   ├── development/          Principles, standards, patterns, lessons
│   ├── modules/              Module documentation
│   └── configuration.md      .env parameters
└── en/                       English translations
```

## Reading order

1. [development/principles.md](en/development/principles.md) — key
   concepts (layers, modularity, ownership) and principles
   (SOLID, DRY, KISS, YAGNI).
2. [development/standards.md](en/development/standards.md) — how we write
   code, commit, and verify changes.
3. [development/patterns.md](en/development/patterns.md) — how the
   principles are implemented (ports, jobs, stash, errors).
4. [development/lessons.md](en/development/lessons.md) — short practical
   lessons; read before non-trivial edits.
5. [configuration.md](en/configuration.md) — all `.env` parameters.
6. Modules (`en/modules/`) — growing:
   [core.md](en/modules/core.md) ✚, [analytics.md](en/modules/analytics.md) ✚,
   [seo.md](en/modules/seo.md) ✚, [reviews.md](en/modules/reviews.md) ✚;
   legal, finance, infographics, bot, user — in progress.

## Conventions

- **Russian is the source of truth.** English versions are translations
  kept in sync with RU.
- **Docstrings** describe the contract (signatures, caps, guards);
  **this documentation** describes the system (purpose, use cases,
  dependencies). Docs reference code; code does not duplicate docs.
- **ADRs** (`adr/`) are for decisions with alternatives that must not be
  silently changed. Everything else goes into development/ or module docs.
- The local `ARCHITECTURE.md` draft in the repo root is not committed
  (via `.git/info/exclude`); its content is being migrated to patterns.md.

## How to extend

New module or a non-trivial feature → update the matching
`modules/<name>.md` (or create one using the template from patterns.md,
"Module doc template" section) in the same PR as the code.
