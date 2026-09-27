from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import (
    UUIDBase,
    str_128,
    str_255,
    timestamp,
)


class User(UUIDBase):
    __tablename__ = "users"

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        default=True,
    )
    created_at: Mapped[timestamp]

    identities: Mapped[list["UserIdentity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserIdentity(UUIDBase):
    # TODO(api): account linking "bot -> site" — never split a user into two accounts.
    # When the site exists, registration must first RECOGNIZE an existing user
    # ("Login with Telegram" / one-time link code issued by the bot) and attach
    # identity(password) to the ALREADY existing User instead of creating a new one.
    # Otherwise the telegram identity stays bound to the old User, the new one
    # "hangs" disconnected from the bot, and linking hits UNIQUE(provider, external_id).
    # Keep in mind: once the user has ever talked to the bot, an "internal" link
    # button on the site cannot work either — the telegram identity is already owned
    # by a different User, so only a merge policy (move data to the account that
    # holds the business data, usually the site) can fix it, which is why
    # prevention (recognize before create) is far better than merging

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_id",
            name="uq_user_identities_provider_external_id",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str_128]
    external_id: Mapped[str_255]
    created_at: Mapped[timestamp]

    user: Mapped[User] = relationship(back_populates="identities")
