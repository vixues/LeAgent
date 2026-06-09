"""Base SQLModel classes with common fields."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _naive_utc_now() -> datetime:
    """UTC "now" as a naive datetime, matching PostgreSQL ``timestamp`` columns.

    Timezone-aware values on ORM inserts against ``DateTime()`` (no tz) break
    asyncpg encoding; see :func:`naive_utc_for_db_column` and
    ``session.store``'s chat timestamp normalization for the symmetric path.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def naive_utc_for_db_column(dt: datetime | None) -> datetime | None:
    """Coerce a datetime for SQL ``DateTime()`` columns without time zone.

    PostgreSQL ``timestamp without time zone`` and asyncpg expect naive
    parameters. If *dt* is timezone-aware, convert to UTC then strip
    ``tzinfo``. Naive values are returned unchanged (callers treat them as
    UTC wall time matching stored rows).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


class TimestampMixin(SQLModel):
    """Mixin providing created_at and updated_at timestamps."""

    created_at: datetime = Field(default_factory=_naive_utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=_naive_utc_now, nullable=False)


class UUIDMixin(SQLModel):
    """Mixin providing UUID primary key."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)


class TenantMixin(SQLModel):
    """Optional multi-tenant scoping.

    ``workspace_id`` is intentionally nullable + indexed: existing rows carry
    ``NULL`` and are implicitly owned by the user's personal workspace; new
    rows populate it from the ``TenantContext`` contextvar. All repository
    queries that extend the tenant-scoped repository pattern
    filter on this column automatically.
    """

    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)


class BaseModel(UUIDMixin, TimestampMixin, SQLModel):
    """Base model with UUID and timestamps."""

    pass


class TenantBaseModel(UUIDMixin, TimestampMixin, TenantMixin, SQLModel):
    """Base model for tenant-scoped entities."""

    pass


class SoftDeleteMixin(SQLModel):
    """Mixin for soft delete functionality."""

    is_deleted: bool = Field(default=False, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)


def utc_now() -> datetime:
    """Return current UTC time as a naive datetime (convention: UTC wall time)."""
    return _naive_utc_now()
