from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base import BaseService
from src.modules.user.enums import Provider
from src.modules.user.models import User
from src.modules.user.repository import UserIdentityRepository, UserRepository


class UserService(BaseService):
    def __init__(
        self,
        session: AsyncSession,
        users: UserRepository,
        identities: UserIdentityRepository,
    ) -> None:
        super().__init__(session)
        self.users = users
        self.identities = identities

    # TODO(api): once the platform (site) exists, stop auto-creating a user on every
    # command. If the telegram identity is not found — do NOT create one; tell the
    # user to authorize/register on the site and link accounts via a one-time code
    # (identity attached to an existing User). This prevents account splitting that
    # makes linking impossible later. Details — see UserIdentity in models.py.
    async def get_or_create(self, telegram_id: int) -> User:
        external_id = str(telegram_id)
        user = await self._find_user(Provider.TELEGRAM, external_id)
        if user is not None:
            return user

        try:
            user = await self.users.add({})
            await self.identities.add(
                {
                    "user_id": user.id,
                    "provider": Provider.TELEGRAM,
                    "external_id": external_id,
                }
            )
        except IntegrityError:
            await self.session.rollback()
            user = await self._find_user(Provider.TELEGRAM, external_id)
            if user is None:
                raise
            return user

        await self.session.commit()
        return user

    async def _find_user(self, provider: Provider, external_id: str) -> User | None:
        identity = await self.identities.get_one(
            provider=provider, external_id=external_id
        )
        if identity is None:
            return None
        return await self.users.get_one(id=identity.user_id)


def get_user_service(session: AsyncSession) -> UserService:
    return UserService(
        session,
        users=UserRepository(session),
        identities=UserIdentityRepository(session),
    )
