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
