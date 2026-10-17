# Practical Lessons

Rules proven by real mistakes in the project. Short takeaways without
incident narratives; context and the "why" land in the matching module
documentation (`docs/*/modules/`).

## Files and encoding

- Never use PowerShell cmdlets (`Set-Content`/`Add-Content`) on files
  with RU/emoji: PS 5.1 rewrites them as ANSI. Edit via editing tools,
  or `git checkout` + re-apply the patch.
- After edits under `src/` — integrity check: search for bytes
  `EF BF BD` (replacement char); must be 0.

## Money

- `Decimal` only, never `float`: `Decimal("1.10") == 1.10` is `False`.
  Comparison literals are `Decimal(...)` too.

## Data and storage

- Real files (XLSX/CSV) differ from synthetic ones: multiple sheets,
  summary blocks on top, neighbouring sheets. Real-export fixtures live
  in `backend/tests/fixtures/`; every parser is verified against them.
- Redis: TTL is mandatory for everything written (stash, job keys,
  service sets); byte caps on everything user-supplied. `maxmemory` +
  `volatile-ttl` (config/redis.conf) guard against OOM.
- Job-only stash keys are not written in inline mode — no dead blobs.

## Interface

- Telegram limits: `copy_text` ≤ 256 chars; keyboards ~10 KB /
  100 buttons (paginate); media captions ≤ 1024 chars.

## Process

- Stacked PRs: branch over branch, PR body says "Stacked on #NN —
  merge that one first"; after the lower PR merges, the upper one
  shrinks automatically.
- Smokes instead of unit tests: a script in a temp folder
  (`PYTHONIOENCODING='utf-8'`, `PYTHONPATH='.'`, run from `backend/`
  via `uv run python`), happy path + error paths + regressions on
  fixtures.
