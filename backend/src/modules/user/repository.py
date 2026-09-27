from src.core.base import BaseRepository
from src.modules.user.models import User, UserIdentity


class UserRepository(BaseRepository[User]):
    model = User


class UserIdentityRepository(BaseRepository[UserIdentity]):
    model = UserIdentity
