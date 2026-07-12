"""Chat project management and unlock-token helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, text
from sqlmodel import col, select

from leagent.config.settings import get_settings
from leagent.db.models.base import utc_now
from leagent.db.models.chat_project import ChatProject
from leagent.db.models.message import ChatSession
from leagent.db.service import DatabaseService
from leagent.db.sqlite_compat import (
    load_entity_by_id,
    parse_uuid_stored,
    same_user_id,
    session_dialect_name,
    sqlite_parent_id_text,
)
from leagent.services.auth.tokens import TokenError, decode_token, mint_token
from leagent.services.chat.project_files import (
    create_project_folder,
    ensure_chat_project_files_root,
    ensure_project_folder,
    ensure_projects_parent_folder,
    soft_delete_project_folder,
)
from leagent.utils.crypto import hash_password, verify_password

PROJECT_UNLOCK_AUDIENCE = "chat_project_unlock"
PROJECT_UNLOCK_TTL_SECONDS = 12 * 60 * 60


@dataclass(slots=True)
class ChatProjectReadModel:
    id: UUID
    user_id: UUID
    workspace_id: UUID | None
    folder_id: UUID | None
    name: str
    description: str | None
    design_context: str | None
    settings: str | None
    has_password: bool
    session_count: int
    created_at: datetime
    updated_at: datetime


class ChatProjectService:
    """Persistence and access-control helpers for chat projects."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    @property
    def _token_secret(self) -> str:
        settings = get_settings()
        return settings.files.signed_url_secret or "leagent-local-secret"

    def mint_unlock_token(self, *, project_id: UUID, user_id: UUID) -> tuple[str, int]:
        exp = int(time.time()) + PROJECT_UNLOCK_TTL_SECONDS
        token = mint_token(
            {
                "aud": PROJECT_UNLOCK_AUDIENCE,
                "scope": "chat_project",
                "pid": str(project_id),
                "uid": str(user_id),
                "exp": exp,
            },
            self._token_secret,
        )
        return token, exp

    def verify_unlock_token(self, token: str | None, *, project_id: UUID, user_id: UUID) -> bool:
        if not token:
            return False
        try:
            payload = decode_token(
                token,
                self._token_secret,
                audience=PROJECT_UNLOCK_AUDIENCE,
                options={"require_exp": True},
            )
        except TokenError:
            return False
        return (
            payload.get("scope") == "chat_project"
            and str(payload.get("pid")) == str(project_id)
            and str(payload.get("uid")) == str(user_id)
        )

    @staticmethod
    def to_read(project: ChatProject, *, session_count: int = 0) -> ChatProjectReadModel:
        return ChatProjectReadModel(
            id=project.id,
            user_id=project.user_id,
            workspace_id=project.workspace_id,
            folder_id=project.folder_id,
            name=project.name,
            description=project.description,
            design_context=project.design_context,
            settings=project.settings,
            has_password=bool(project.password_hash),
            session_count=session_count,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    async def _count_sessions(self, project_id: UUID) -> int:
        async with self._db.session() as db:
            if session_dialect_name(db) == "sqlite":
                p_txt = await sqlite_parent_id_text(db, "chat_projects", project_id)
                result = await db.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM chat_sessions
                        WHERE lower(replace(CAST(project_id AS TEXT), '-', '')) = :pid_plain
                          AND is_active = 1
                        """
                    ),
                    {"pid_plain": p_txt.replace("-", "").lower()},
                )
                return int(result.scalar_one() or 0)

            result = await db.execute(
                select(func.count()).select_from(ChatSession).where(
                    ChatSession.project_id == project_id,
                    ChatSession.is_active == True,  # noqa: E712
                )
            )
            return int(result.scalar_one() or 0)

    async def _ensure_read_folder(
        self,
        read: ChatProjectReadModel,
        *,
        user_id: UUID,
    ) -> ChatProjectReadModel:
        if read.folder_id is not None:
            return read
        project = await self.get_project(read.id, user_id=user_id)
        if project is None:
            return read
        space = await ensure_project_folder(self._db, project)
        return ChatProjectReadModel(
            id=read.id,
            user_id=read.user_id,
            workspace_id=read.workspace_id,
            folder_id=space.folder_id,
            name=read.name,
            description=read.description,
            design_context=read.design_context,
            settings=read.settings,
            has_password=read.has_password,
            session_count=read.session_count,
            created_at=read.created_at,
            updated_at=read.updated_at,
        )

    async def list_projects(self, user_id: UUID) -> list[ChatProjectReadModel]:
        async with self._db.session() as db:
            if session_dialect_name(db) == "sqlite":
                u_txt = await sqlite_parent_id_text(db, "users", user_id)
                rows = (
                    await db.execute(
                        text(
                            """
                            SELECT p.id, p.user_id, p.workspace_id, p.folder_id, p.name, p.description,
                                   p.design_context, p.settings, p.password_hash,
                                   p.created_at, p.updated_at,
                                   COUNT(s.id) AS session_count
                            FROM chat_projects p
                            LEFT JOIN chat_sessions s
                              ON lower(replace(CAST(s.project_id AS TEXT), '-', ''))
                               = lower(replace(CAST(p.id AS TEXT), '-', ''))
                             AND s.is_active = 1
                            WHERE CAST(p.user_id AS TEXT) = :uid
                              AND p.is_deleted = 0
                            GROUP BY p.id, p.user_id, p.workspace_id, p.folder_id, p.name, p.description,
                                     p.design_context, p.settings, p.password_hash,
                                     p.created_at, p.updated_at
                            ORDER BY p.updated_at DESC
                            """
                        ),
                        {"uid": u_txt},
                    )
                ).mappings().all()
                out: list[ChatProjectReadModel] = []
                for row in rows:
                    out.append(
                        ChatProjectReadModel(
                            id=parse_uuid_stored(str(row["id"])),
                            user_id=parse_uuid_stored(str(row["user_id"])),
                            workspace_id=(
                                parse_uuid_stored(str(row["workspace_id"]))
                                if row["workspace_id"] is not None
                                else None
                            ),
                            folder_id=(
                                parse_uuid_stored(str(row["folder_id"]))
                                if row.get("folder_id") is not None
                                else None
                            ),
                            name=str(row["name"]),
                            description=(
                                str(row["description"]) if row["description"] is not None else None
                            ),
                            design_context=(
                                str(row["design_context"])
                                if row["design_context"] is not None
                                else None
                            ),
                            settings=str(row["settings"]) if row["settings"] is not None else None,
                            has_password=bool(row["password_hash"]),
                            session_count=int(row["session_count"] or 0),
                            created_at=row["created_at"],  # type: ignore[arg-type]
                            updated_at=row["updated_at"],  # type: ignore[arg-type]
                        )
                    )
            else:
                count_expr = func.count(ChatSession.id).label("session_count")
                result = await db.execute(
                    select(ChatProject, count_expr)
                    .outerjoin(
                        ChatSession,
                        (ChatSession.project_id == ChatProject.id)
                        & (ChatSession.is_active == True),  # noqa: E712
                    )
                    .where(
                        ChatProject.user_id == user_id,
                        ChatProject.is_deleted == False,  # noqa: E712
                    )
                    .group_by(ChatProject.id)
                    .order_by(col(ChatProject.updated_at).desc())
                )
                out = [
                    self.to_read(project, session_count=int(count or 0))
                    for project, count in result.all()
                ]

        ensured: list[ChatProjectReadModel] = []
        for read in out:
            ensured.append(await self._ensure_read_folder(read, user_id=user_id))
        return ensured

    async def get_project(self, project_id: UUID, *, user_id: UUID) -> ChatProject | None:
        async with self._db.session() as db:
            project = await load_entity_by_id(
                db,
                ChatProject,
                project_id,
                parent_table="chat_projects",
            )
            if project is None or project.is_deleted:
                return None
            if not same_user_id(project.user_id, user_id):
                return None
            return project

    async def get_project_read(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ChatProjectReadModel | None:
        project = await self.get_project(project_id, user_id=user_id)
        if project is None:
            return None
        space = await ensure_project_folder(self._db, project)
        # Reload so folder_id is current after lazy ensure.
        project = await self.get_project(project_id, user_id=user_id)
        if project is None:
            return None
        if project.folder_id is None:
            project.folder_id = space.folder_id
        return self.to_read(project, session_count=await self._count_sessions(project.id))

    async def create_project(
        self,
        *,
        user_id: UUID,
        name: str,
        description: str | None = None,
        design_context: str | None = None,
        settings: str | None = None,
        password: str | None = None,
    ) -> ChatProject:
        project_id = uuid4()
        async with self._db.session() as db:
            parent = await ensure_projects_parent_folder(db, user_id=user_id)
            folder = await create_project_folder(
                db,
                user_id=user_id,
                name=name,
                parent=parent,
            )
            project = ChatProject(
                id=project_id,
                user_id=user_id,
                name=name,
                description=description,
                design_context=design_context,
                settings=settings,
                password_hash=hash_password(password) if password else None,
                folder_id=folder.id,
            )
            db.add(project)
            await db.flush()
            await db.refresh(project)
        ensure_chat_project_files_root(project.id)
        return project

    async def update_project(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        name: str | None = None,
        description: str | None = None,
        design_context: str | None = None,
        settings: str | None = None,
        password: str | None = None,
        clear_password: bool = False,
    ) -> ChatProject | None:
        from leagent.db.models.folder import Folder

        async with self._db.session() as db:
            project = await load_entity_by_id(
                db,
                ChatProject,
                project_id,
                parent_table="chat_projects",
            )
            if project is None or project.is_deleted or not same_user_id(project.user_id, user_id):
                return None
            if name is not None:
                project.name = name
                if project.folder_id is not None:
                    folder = await load_entity_by_id(
                        db, Folder, project.folder_id, parent_table="folders"
                    )
                    if (
                        folder is not None
                        and not folder.is_deleted
                        and same_user_id(folder.user_id, user_id)
                    ):
                        folder.name = name
                        folder.updated_at = utc_now()
                        db.add(folder)
            if description is not None:
                project.description = description
            if design_context is not None:
                project.design_context = design_context
            if settings is not None:
                project.settings = settings
            if clear_password:
                project.password_hash = None
            elif password:
                project.password_hash = hash_password(password)
            project.updated_at = utc_now()
            db.add(project)
            await db.flush()
            await db.refresh(project)
            return project

    async def delete_project(self, project_id: UUID, *, user_id: UUID) -> bool:
        async with self._db.session() as db:
            project = await load_entity_by_id(
                db,
                ChatProject,
                project_id,
                parent_table="chat_projects",
            )
            if project is None or project.is_deleted or not same_user_id(project.user_id, user_id):
                return False
            await soft_delete_project_folder(
                db, folder_id=project.folder_id, user_id=user_id
            )
            project.is_deleted = True
            project.deleted_at = utc_now()
            project.updated_at = project.deleted_at
            db.add(project)
            if session_dialect_name(db) == "sqlite":
                p_txt = await sqlite_parent_id_text(db, "chat_projects", project_id)
                await db.execute(
                    text(
                        """
                        UPDATE chat_sessions
                        SET project_id = NULL
                        WHERE lower(replace(CAST(project_id AS TEXT), '-', '')) = :pid_plain
                        """
                    ),
                    {"pid_plain": p_txt.replace("-", "").lower()},
                )
            else:
                await db.execute(
                    ChatSession.__table__.update()
                    .where(ChatSession.project_id == project_id)
                    .values(project_id=None)
                )
            return True

    async def verify_project_password(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        password: str,
    ) -> bool:
        project = await self.get_project(project_id, user_id=user_id)
        if project is None or not project.password_hash:
            return False
        return verify_password(password, project.password_hash)

    async def require_project_access(
        self,
        project_id: UUID | None,
        *,
        user_id: UUID,
        unlock_token: str | None = None,
    ) -> ChatProject | None:
        if project_id is None:
            return None
        project = await self.get_project(project_id, user_id=user_id)
        if project is None:
            raise PermissionError("Project not found")
        if project.password_hash and not self.verify_unlock_token(
            unlock_token,
            project_id=project.id,
            user_id=user_id,
        ):
            raise PermissionError("Project locked")
        return project

    async def require_session_project_access(
        self,
        session: ChatSession,
        *,
        user_id: UUID,
        unlock_token: str | None = None,
    ) -> None:
        await self.require_project_access(
            session.project_id,
            user_id=user_id,
            unlock_token=unlock_token,
        )
