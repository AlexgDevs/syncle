# Module user

Users and their identities (Telegram for now). A minimal scaffold for
a future platform.

## Boundaries

- **Does:** resolve/create a user by external identifier
  (`get_or_create(telegram_id)`), store user ↔ identity links.
- **Does not:** no authorization, roles, or profiles — all deferred
  until the platform exists.

## Public API

`get_user_service(session) -> UserService` — the only session-scoped
factory in the project (not lru_cache: the service needs an
`AsyncSession`).

| Method | Purpose |
|---|---|
| `async get_or_create(telegram_id) -> User` | find identity (TELEGRAM, str(telegram_id)); create User + identity when missing; on `IntegrityError` race — rollback and re-find |

## Data

- `User` — is_active, created_at, identities relation.
- `UserIdentity` — user_id, provider, external_id;
  `UNIQUE(provider, external_id)`; `Provider.TELEGRAM` is the only
  provider.
- Repositories: `UserRepository`, `UserIdentityRepository`
  (BaseRepository).

## Dependencies

core: `database`, `base`. No other modules are involved.

## Use cases

`UserMiddleware` (bot) calls `get_or_create` on every message and
callback — the only consumer in the current code. Explicit registration
(site + one-time link code) — a TODO in `models.py` (the
merge-vs-prevent identity policy is not decided yet).

## Related issues/PRs

M0/F01 scaffold; the linking-policy TODO lives in the `UserIdentity`
docstring.
