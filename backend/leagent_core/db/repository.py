"""Repository base class"""

from __future__ import annotations

from typing import Any, Generic, Iterable, Sequence, TypeVar
from uuid import UUID

ModelT = TypeVar("ModelT")


class TenantScopedRepository(Generic[ModelT]):
    """CRUD helper — no tenant scoping in standalone local deployment."""

    model: type[Any]

    def __init__(self, session: Any) -> None:
        self.session = session

    async def get(self, id_: UUID) -> ModelT | None:
        from sqlmodel import select

        stmt = select(self.model).where(self.model.id == id_)
        result = await self.session.exec(stmt)
        return result.first()

    async def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        extra_filters: Iterable[Any] = (),
    ) -> Sequence[ModelT]:
        from sqlmodel import select

        stmt = select(self.model).offset(offset).limit(limit)
        for f in extra_filters:
            stmt = stmt.where(f)
        result = await self.session.exec(stmt)
        return list(result.all())

    async def add(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)


__all__ = ["TenantScopedRepository"]
