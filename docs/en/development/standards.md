# Development Standards

Unified coding, verification, and delivery rules for Syncle.
The concepts and principles behind these rules — in
[principles.md](principles.md).

## Languages

| Where | Language |
|---|---|
| Module code (`src/modules/`, `src/core/`), docstrings, names | EN |
| LLM prompts, progress step codes (`PROGRESS_STEPS`) | EN |
| Bot texts, replies/alerts, report renderers (`src/bot/`) | RU |
| User-facing module content (RU fee descriptions, alerts) | RU |
| Documentation (`docs/`), ADRs | RU (EN is a translation) |

Code comments are EN. The language rule always yields to user-facing
content: it is RU regardless of file location (precedent:
`modules/finance/tariffs.py` stores RU hidden-fee descriptions).

## Layers and dependencies

```
bot / worker / api  →  modules  →  core
```

- `core` never imports `modules` or entry points. Check:
  `grep -r "from src.modules" src/core` must be empty.
- `modules` never import aiogram and hold no Telegram types. Check:
  `grep -r "aiogram" src/modules` must be empty.
- Business logic lives in the module; interfaces (bot, worker, api) are
  thin adapters with no domain decisions.

## Code style

- Formatting and typing via `black` and `mypy` from `backend/`:
  `uv run black src && uv run mypy src`. Both green — DoD.
- Python 3.14, dependencies via `uv`.
- Pydantic v2: domain schemas in the module's `schemas.py`; `Decimal`
  for all money and percentages (never `float`).
- Singleton factories — `@lru_cache def get_x_service()` (following
  pydantic-settings `get_settings()`).
- Constants: module-private `_CONST` → package `constants.py` when
  2+ modules need it → `core/settings.py` if it changes per deploy
  (details in patterns.md).
- Naming: `SCREAMING_SNAKE` constants, `_` prefix for private.

## Working with files

- Edit code via editing tools (edit/write) or `git checkout` + re-apply
  the patch. Do **not** use PowerShell cmdlets (`Set-Content`/
  `Add-Content`) on files with RU/emoji — PS 5.1 rewrites them as ANSI
  (see lessons.md).
- Integrity check after edits under `src/` — search for bytes
  `EF BF BD` (replacement char): 0 matches.

## Commits and branches

- Format: `feat|fix|chore(<scope>): short summary #NN` — issue number
  in the header.
- A commit is one logical unit (module or layer); mixing unrelated
  changes is forbidden.
- Feature branch — from `dev`: `alexgdev-<topic>`. Stacked PRs allowed:
  branch A on top of branch B, PRs merged in order.
- PR body: `Closes #NN`, sections What / Verification.
- Commit/push/PR only on the owner's explicit command.

## Definition of Done

1. `uv run black src` + `uv run mypy src` — clean.
2. A smoke script for non-trivial logic (in a temp folder, not in git)
   with real fixtures from `backend/tests/fixtures/`.
3. Live bot run (restart + manual scene check).
4. The user-facing layer (adapter texts/keyboards) updated together
   with logic; no stubs in production.
5. Module docstring reflects the contract (caps, guards, error paths).

## Review checklist

- Imports do not break layer direction.
- No `float` for money; money is `Decimal`.
- No aiogram in modules; no RU strings in modules without a user-facing
  role.
- All new Redis keys have TTL; byte caps on everything written to stash.
- Domain errors go through the `SyncleError` tree; user-facing RU text
  is mapped in `bot/errors.py`.
- Interface limits respected (message/keyboard caps — see lessons.md).

## What we do not do

- Unit tests in the repository (not adopted at this stage; smoke scripts
  and fixtures instead).
- Silent rewrites of merged code.
- Secrets in git: `.env` is never committed; local `ARCHITECTURE.md`
  lives behind `.git/info/exclude`.
