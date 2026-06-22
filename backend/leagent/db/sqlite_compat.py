"""SQLite-specific helpers: UUID text matching, enum coercion, dialect checks.

Centralizes logic used when ``aiosqlite`` stores UUIDs and enums in shapes that
differ from what SQLAlchemy's default loaders expect for PostgreSQL-oriented
schemas.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, TypeVar
from uuid import UUID

from sqlalchemy import text
from sqlmodel.ext.asyncio.session import AsyncSession

_PARENT_ID_TABLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# Tables we may embed in ``SELECT ... FROM {table}`` after validation only.
PARENT_ID_TABLES: frozenset[str] = frozenset(
    {
        "users",
        "workspaces",
        "pet_projects",
        "chat_projects",
        "files",
        "chat_sessions",
        "roles",
        "folders",
        "todos",
        "todo_checklist_items",
        "tasks",
        "notifications",
        "coding_projects",
    }
)

_T = TypeVar("_T")


async def load_entity_by_id(
    session: AsyncSession,
    model_cls: type[_T],
    entity_id: UUID,
    *,
    parent_table: str,
) -> _T | None:
    """ORM ``get`` by primary key with SQLite stored-UUID normalization."""
    if parent_table not in PARENT_ID_TABLES:
        raise ValueError(f"unsupported parent_table for id lookup: {parent_table}")
    if session_dialect_name(session) == "sqlite":
        id_txt = await sqlite_parent_id_text(session, parent_table, entity_id)
        logical = parse_uuid_stored(id_txt)
        return await session.get(model_cls, logical)
    return await session.get(model_cls, entity_id)


def session_dialect_name(session: AsyncSession) -> str:
    """Return ``bind.dialect.name`` (e.g. ``sqlite``, ``postgresql``)."""
    bind = session.get_bind()
    return getattr(getattr(bind, "dialect", None), "name", "") or ""


def parse_uuid_stored(s: str | object) -> UUID:
    """Parse ``id`` values as returned by SQLite ``CAST(... AS TEXT)``."""
    t = str(s).strip()
    if len(t) == 32 and "-" not in t:
        return UUID(hex=t)
    return UUID(t)


def same_user_id(a: object, b: object) -> bool:
    """Compare user ids when SQLite / drivers disagree on UUID vs hex text."""
    try:
        return UUID(str(a)) == UUID(str(b))
    except (ValueError, TypeError, AttributeError):
        return str(a) == str(b)


async def load_user_by_id(session: AsyncSession, user_id: UUID):
    """No-op — user model removed."""
    return None


async def sqlite_user_role_names(session: AsyncSession, user_id: UUID) -> list[str]:
    return ["admin"]


async def sqlite_user_permission_keys(session: AsyncSession, user_id: UUID) -> list[str]:
    return ["*"]


async def load_role_by_id(session: AsyncSession, role_id: UUID):
    return None
    return await session.get(Role, role_id)


async def load_chat_session_by_id(
    session: AsyncSession,
    chat_session_id: UUID,
    *,
    owner_user_id: UUID | None = None,
):
    """Load :class:`ChatSession` by PK; optional owner check (SQLite UUID-safe)."""
    from sqlmodel import select

    from leagent.db.models.message import ChatSession

    if session_dialect_name(session) == "sqlite":
        s_txt = await sqlite_parent_id_text(session, "chat_sessions", chat_session_id)
        logical = parse_uuid_stored(s_txt)
        row = await session.get(ChatSession, logical)
        if row is None:
            return None
        if owner_user_id is not None and not same_user_id(row.user_id, owner_user_id):
            return None
        return row
    stmt = select(ChatSession).where(ChatSession.id == chat_session_id)
    if owner_user_id is not None:
        stmt = stmt.where(ChatSession.user_id == owner_user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def sqlite_parent_id_text(session: AsyncSession, table: str, logical: UUID) -> str:
    """Return the exact ``id`` string stored in SQLite for FK child inserts."""
    if table not in PARENT_ID_TABLES or not _PARENT_ID_TABLE_RE.fullmatch(table):
        raise ValueError(f"unsupported table for id lookup: {table}")
    full = str(logical)
    plain = full.replace("-", "").lower()
    result = await session.execute(
        text(
            f"SELECT CAST(id AS TEXT) FROM {table} "
            "WHERE lower(CAST(id AS TEXT)) = lower(:full) "
            "OR lower(replace(CAST(id AS TEXT), '-', '')) = :plain"
        ),
        {"full": full, "plain": plain},
    )
    row = result.first()
    if row is None:
        return full
    return str(row[0])


def file_type_from_db(raw: object):
    """Map DB ``file_type`` (``IMAGE`` or ``image``) to :class:`FileType`."""
    from leagent.db.models.file import FileType

    s = str(raw).strip()
    if s in FileType.__members__:
        return FileType[s]
    low = s.lower()
    for ft in FileType:
        if ft.value == low:
            return ft
    return FileType.OTHER


def file_status_from_db(raw: object):
    """Map DB ``status`` (``PROCESSED`` or ``processed``) to :class:`FileStatus`."""
    from leagent.db.models.file import FileStatus

    s = str(raw).strip()
    if s in FileStatus.__members__:
        return FileStatus[s]
    low = s.lower()
    for st in FileStatus:
        if st.value == low:
            return st
    return FileStatus.UPLOADED


def file_model_from_sqlite_row(row: Mapping[str, Any]):
    """Hydrate :class:`File` from a raw SQLite row (avoids broken enum coercion)."""
    from leagent.db.models.file import File as FileModel

    d = dict(row)
    return FileModel(
        id=parse_uuid_stored(str(d["id"])),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        is_deleted=bool(d.get("is_deleted", False)),
        deleted_at=d.get("deleted_at"),
        name=d["name"],
        original_name=d["original_name"],
        file_type=file_type_from_db(d["file_type"]),
        mime_type=d.get("mime_type"),
        size=int(d["size"]),
        status=file_status_from_db(d["status"]),
        user_id=parse_uuid_stored(str(d["user_id"])) if d.get("user_id") is not None else None,
        workspace_id=(
            parse_uuid_stored(str(d["workspace_id"]))
            if d.get("workspace_id") is not None
            else None
        ),
        folder_id=(
            parse_uuid_stored(str(d["folder_id"])) if d.get("folder_id") is not None else None
        ),
        session_id=(
            parse_uuid_stored(str(d["session_id"])) if d.get("session_id") is not None else None
        ),
        storage_path=d["storage_path"],
        storage_bucket=d.get("storage_bucket"),
        checksum=d.get("checksum"),
        extracted_text=d.get("extracted_text"),
        file_metadata=d.get("file_metadata"),
        page_count=d.get("page_count"),
        has_ocr=bool(d.get("has_ocr", False)),
        ocr_language=d.get("ocr_language"),
        embedding_id=d.get("embedding_id"),
        is_indexed=bool(d.get("is_indexed", False)),
        expires_at=d.get("expires_at"),
    )


def workspace_member_role_from_db(raw: object):
    return str(raw).strip().lower()


__all__ = [
    "PARENT_ID_TABLES",
    "session_dialect_name",
    "parse_uuid_stored",
    "same_user_id",
    "sqlite_parent_id_text",
    "load_user_by_id",
    "load_role_by_id",
    "load_chat_session_by_id",
    "load_entity_by_id",
    "sqlite_user_role_names",
    "sqlite_user_permission_keys",
    "file_type_from_db",
    "file_status_from_db",
    "file_model_from_sqlite_row",
    "workspace_member_role_from_db",
]
