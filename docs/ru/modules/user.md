# Модуль user

Пользователи и их идентичности (сейчас только Telegram). Минимальный
модуль-заготовка под будущую платформу.

## Границы

- **Делает:** резолвит/создаёт пользователя по внешнему идентификатору
  (`get_or_create(telegram_id)`), хранит связи user ↔ identity.
- **Не делает:** нет авторизации, ролей, профилей, API — всё это
  отложено до появления платформы.

## Публичный API

`get_user_service(session) -> UserService` — **единственная
session-scoped** фабрика в проекте (не lru_cache: сервису нужна
`AsyncSession`).

| Метод | Назначение |
|---|---|
| `async get_or_create(telegram_id) -> User` | найти identity (TELEGRAM, str(telegram_id)); создать User + identity при отсутствии; при гонке `IntegrityError` — rollback и повторный поиск |

## Данные

- `User` — is_active, created_at, relation identities.
- `UserIdentity` — user_id, provider, external_id; `UNIQUE(provider,
  external_id)`; `Provider.TELEGRAM` — единственный провайдер.
- Репозитории: `UserRepository`, `UserIdentityRepository`
  (BaseRepository).

## Зависимости

core: `database`, `base`. Других модулей не задействует.

## Кейсы

`UserMiddleware` (bot) вызывает `get_or_create` на каждом сообщении и
колбэке — это единственный потребитель в текущем коде. Явная
регистрация (сайт + одноразовый код привязки) — TODO в `models.py`
(политика merge-vs-prevent идентичностей ещё не решена).

## Связанные issues/PR

Заготовка M0/F01; TODO по linking-политике — в docstring
`UserIdentity`.
