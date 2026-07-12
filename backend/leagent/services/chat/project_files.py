"""Shared file-space helpers for chat projects.

Each :class:`~leagent.db.models.chat_project.ChatProject` owns:

* a catalog :class:`~leagent.db.models.folder.Folder` (visible on ``/folders``)
* an on-disk root under ``$LEAGENT_HOME/working/projects/<project_id>/``

All chat sessions with that ``project_id`` share the same folder + disk root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import select

from leagent.config.constants import WORKING_DIR
from leagent.db.models.base import utc_now
from leagent.db.models.chat_project import ChatProject
from leagent.db.models.file import File as FileModel
from leagent.db.models.folder import Folder
from leagent.db.models.message import ChatSession
from leagent.db.service import DatabaseService
from leagent.db.sqlite_compat import (
    load_entity_by_id,
    same_user_id,
)

CHAT_PROJECTS_ROOT_SENTINEL = "__leagent_chat_projects_root__"
CHAT_PROJECTS_ROOT_NAME = "项目"
CHAT_PROJECT_FOLDER_ICON = "📂"


def chat_project_files_root(project_id: UUID | str) -> Path:
    """Absolute on-disk root for a chat project's shared workspace."""
    return (WORKING_DIR / "projects" / str(project_id)).expanduser().resolve()


def ensure_chat_project_files_root(project_id: UUID | str) -> Path:
    """Create the project disk root if missing and return it."""
    root = chat_project_files_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass(slots=True)
class ChatProjectFileSpace:
    """Resolved shared file space for a chat project."""

    project_id: UUID
    folder_id: UUID
    files_root: str


async def _find_projects_parent_folder(
    db_session: object,
    *,
    user_id: UUID,
) -> Folder | None:
    """Return the per-user 「项目」parent folder, if it already exists."""
    result = await db_session.exec(  # type: ignore[attr-defined]
        select(Folder).where(
            Folder.user_id == user_id,
            Folder.is_deleted == False,  # noqa: E712
            Folder.parent_id == None,  # noqa: E711
            Folder.description == CHAT_PROJECTS_ROOT_SENTINEL,
        )
    )
    return result.first()


async def ensure_projects_parent_folder(
    db_session: object,
    *,
    user_id: UUID,
) -> Folder:
    """Idempotently ensure the per-user parent Folder for chat projects."""
    existing = await _find_projects_parent_folder(db_session, user_id=user_id)
    if existing is not None:
        return existing

    folder = Folder(
        id=uuid4(),
        user_id=user_id,
        name=CHAT_PROJECTS_ROOT_NAME,
        description=CHAT_PROJECTS_ROOT_SENTINEL,
        icon="📁",
        parent_id=None,
        position=0,
    )
    db_session.add(folder)  # type: ignore[attr-defined]
    await db_session.flush()  # type: ignore[attr-defined]
    return folder


async def create_project_folder(
    db_session: object,
    *,
    user_id: UUID,
    name: str,
    parent: Folder,
) -> Folder:
    """Create the catalog Folder for a newly created chat project."""
    folder = Folder(
        id=uuid4(),
        user_id=user_id,
        name=name.strip() or "Untitled",
        description=None,
        icon=CHAT_PROJECT_FOLDER_ICON,
        parent_id=parent.id,
        position=0,
    )
    db_session.add(folder)  # type: ignore[attr-defined]
    await db_session.flush()  # type: ignore[attr-defined]
    return folder


async def ensure_project_folder(
    db: DatabaseService,
    project: ChatProject,
) -> ChatProjectFileSpace:
    """Ensure *project* has a linked Folder + disk root; return the binding.

    Safe to call repeatedly (lazy backfill for pre-migration projects).
    """
    ensure_chat_project_files_root(project.id)

    if project.folder_id is not None:
        async with db.session() as session:
            folder = await load_entity_by_id(
                session, Folder, project.folder_id, parent_table="folders"
            )
            if (
                folder is not None
                and not folder.is_deleted
                and same_user_id(folder.user_id, project.user_id)
            ):
                return ChatProjectFileSpace(
                    project_id=project.id,
                    folder_id=folder.id,
                    files_root=str(chat_project_files_root(project.id)),
                )

    async with db.session() as session:
        fresh = await load_entity_by_id(
            session, ChatProject, project.id, parent_table="chat_projects"
        )
        if fresh is None or fresh.is_deleted:
            raise LookupError("Project not found")

        if fresh.folder_id is not None:
            folder = await load_entity_by_id(
                session, Folder, fresh.folder_id, parent_table="folders"
            )
            if (
                folder is not None
                and not folder.is_deleted
                and same_user_id(folder.user_id, fresh.user_id)
            ):
                ensure_chat_project_files_root(fresh.id)
                return ChatProjectFileSpace(
                    project_id=fresh.id,
                    folder_id=folder.id,
                    files_root=str(chat_project_files_root(fresh.id)),
                )

        parent = await ensure_projects_parent_folder(session, user_id=fresh.user_id)
        folder = await create_project_folder(
            session,
            user_id=fresh.user_id,
            name=fresh.name,
            parent=parent,
        )
        fresh.folder_id = folder.id
        fresh.updated_at = utc_now()
        session.add(fresh)
        await session.flush()
        ensure_chat_project_files_root(fresh.id)
        return ChatProjectFileSpace(
            project_id=fresh.id,
            folder_id=folder.id,
            files_root=str(chat_project_files_root(fresh.id)),
        )


async def resolve_session_project_file_space(
    db: DatabaseService,
    *,
    session_id: UUID,
    user_id: UUID,
) -> ChatProjectFileSpace | None:
    """Resolve shared file space for a chat session, if it belongs to a project."""
    async with db.session() as session:
        chat_session = await load_entity_by_id(
            session, ChatSession, session_id, parent_table="chat_sessions"
        )
        if chat_session is None or not same_user_id(chat_session.user_id, user_id):
            return None
        project_id = chat_session.project_id
        if project_id is None:
            return None
        project = await load_entity_by_id(
            session, ChatProject, project_id, parent_table="chat_projects"
        )
        if project is None or project.is_deleted or not same_user_id(project.user_id, user_id):
            return None

    return await ensure_project_folder(db, project)


async def resolve_project_file_space(
    db: DatabaseService,
    *,
    project_id: UUID,
    user_id: UUID,
) -> ChatProjectFileSpace | None:
    """Resolve shared file space for a chat project id."""
    async with db.session() as session:
        project = await load_entity_by_id(
            session, ChatProject, project_id, parent_table="chat_projects"
        )
        if project is None or project.is_deleted or not same_user_id(project.user_id, user_id):
            return None
    return await ensure_project_folder(db, project)


async def link_file_ids_to_folder(
    db: DatabaseService,
    *,
    file_ids: list[UUID],
    folder_id: UUID,
    user_id: UUID,
) -> int:
    """Attach managed File rows to *folder_id*; return how many were newly linked."""
    if not file_ids:
        return 0

    linked = 0
    async with db.session() as session:
        folder = await load_entity_by_id(
            session, Folder, folder_id, parent_table="folders"
        )
        if folder is None or folder.is_deleted or not same_user_id(folder.user_id, user_id):
            return 0

        for fid in file_ids:
            row = await load_entity_by_id(session, FileModel, fid, parent_table="files")
            if row is None or row.is_deleted or not same_user_id(row.user_id, user_id):
                continue
            if row.folder_id == folder_id:
                continue
            row.folder_id = folder_id
            row.updated_at = utc_now()
            session.add(row)
            linked += 1

        if linked:
            folder.file_count = int(folder.file_count or 0) + linked
            folder.updated_at = utc_now()
            session.add(folder)
            await session.flush()

    return linked


async def soft_delete_project_folder(
    db_session: object,
    *,
    folder_id: UUID | None,
    user_id: UUID,
) -> None:
    """Soft-delete the catalog Folder linked to a chat project (disk root kept)."""
    if folder_id is None:
        return
    folder = await load_entity_by_id(
        db_session, Folder, folder_id, parent_table="folders"  # type: ignore[arg-type]
    )
    if folder is None or folder.is_deleted or not same_user_id(folder.user_id, user_id):
        return
    now = utc_now()
    folder.is_deleted = True
    folder.deleted_at = now
    folder.updated_at = now
    db_session.add(folder)  # type: ignore[attr-defined]
