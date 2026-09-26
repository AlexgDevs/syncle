from sqlalchemy.orm import DeclarativeBase

from src.core.database.mixin import UUIDMixin


class Base(DeclarativeBase):
    pass


class UUIDBase(UUIDMixin, Base):
    __abstract__ = True
