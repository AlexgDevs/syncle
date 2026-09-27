from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.base import UUIDBase


class BaseRepository[T: UUIDBase]:
    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_filtered(
        self,
        limit: int,
        offset: int,
        order_by: ColumnElement[Any] | None = None,
        **filter_by: Any,
    ) -> Sequence[T]:
        query = select(self.model).filter_by(**filter_by)
        if order_by is not None:
            query = query.order_by(order_by)
        query = query.limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_one(self, **filter_by: Any) -> T | None:
        query = select(self.model).filter_by(**filter_by)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def add(self, data: dict[str, Any]) -> T:
        statement = insert(self.model).values(**data).returning(self.model)
        result = await self.session.execute(statement)
        return result.scalar_one()

    async def update(self, id_: UUID, values: dict[str, Any]) -> T | None:
        statement = (
            update(self.model)
            .where(self.model.id == id_)
            .values(**values)
            .returning(self.model)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def delete(self, id_: UUID) -> None:
        statement = delete(self.model).where(self.model.id == id_)
        await self.session.execute(statement)
