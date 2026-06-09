"""Pet Space API — mascot creative projects and library file uploads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Mapping, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from leagent.api.v1.files import (
    FileUploadResponse,
    MAX_FILE_SIZE,
    persist_pet_space_file,
)
from leagent.services.auth import CurrentUserId
from leagent.db import DatabaseService, get_database_service
from leagent.db.models import (
    File as FileModel,
    PetProject,
    PetProjectFile,
)
from leagent.db.sqlite_compat import (
    load_entity_by_id,
    load_user_by_id,
    parse_uuid_stored,
    same_user_id,
    session_dialect_name,
    sqlite_parent_id_text,
)
async def ensure_personal_workspace(session, user):
    from types import SimpleNamespace
    return SimpleNamespace(id=user.id if hasattr(user, 'id') else None)


async def user_can_access_workspace(session, user_id, ws_id):
    return "owner"

router = APIRouter()


class PetProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)


class PetProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    settings: Optional[str] = Field(default=None, max_length=20000)


class PetProjectRead(BaseModel):
    id: UUID
    user_id: UUID
    workspace_id: Optional[UUID]
    name: str
    description: Optional[str]
    settings: Optional[str] = None
    created_at: object
    updated_at: object


class PetProjectFileRead(BaseModel):
    id: UUID
    pet_project_id: UUID
    file_id: UUID
    original_name: str
    mime_type: Optional[str]
    size: int
    created_at: object


class DefaultPetPersonalityRead(BaseModel):
    document: str


def _pet_project_from_sqlite_row(row: Mapping[str, object]) -> PetProject:
    return PetProject(
        id=parse_uuid_stored(str(row["id"])),
        user_id=parse_uuid_stored(str(row["user_id"])),
        workspace_id=(
            parse_uuid_stored(str(row["workspace_id"]))
            if row.get("workspace_id") is not None
            else None
        ),
        name=str(row["name"]),
        description=row.get("description") if row.get("description") is not None else None,
        settings=row.get("settings") if row.get("settings") is not None else None,
        is_deleted=bool(row.get("is_deleted", False)),
        deleted_at=row.get("deleted_at"),
        created_at=row["created_at"],  # type: ignore[arg-type]
        updated_at=row["updated_at"],  # type: ignore[arg-type]
    )


async def _load_pet_project_for_owner_sqlite(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> Mapping[str, object]:
    p_txt = await sqlite_parent_id_text(session, "pet_projects", project_id)
    r = await session.execute(
        text(
            """
            SELECT id, user_id, workspace_id, name, description, settings,
                   created_at, updated_at, is_deleted, deleted_at
            FROM pet_projects
            WHERE CAST(id AS TEXT) = :p
            """
        ),
        {"p": p_txt},
    )
    row = r.mappings().first()
    if row is None or row["is_deleted"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not same_user_id(row["user_id"], user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if row["workspace_id"] is not None:
        ws_uuid = parse_uuid_stored(str(row["workspace_id"]))
        role = await user_can_access_workspace(session, user_id, ws_uuid)
        if role is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return row


async def _active_workspace_id(
    user_id: UUID, db: DatabaseService
) -> tuple[UUID, UUID]:
    return user_id, user_id


async def _require_project(
    project_id: UUID,
    user_id: UUID,
    db: DatabaseService,
) -> PetProject:
    async with db.session() as session:
        if session_dialect_name(session) == "sqlite":
            row = await _load_pet_project_for_owner_sqlite(session, project_id, user_id)
            return _pet_project_from_sqlite_row(row)

        proj = await load_entity_by_id(
            session, PetProject, project_id, parent_table="pet_projects"
        )
        if proj is None or proj.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if not same_user_id(proj.user_id, user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        if proj.workspace_id is not None:
            role = await user_can_access_workspace(session, user_id, proj.workspace_id)
            if role is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return proj


@router.get("/personality/default", response_model=DefaultPetPersonalityRead)
async def get_default_pet_personality(
    _user_id: CurrentUserId,
) -> DefaultPetPersonalityRead:
    """Return the managed default pet personality Markdown document."""
    from leagent.services.chat.pet_personality import get_default_pet_personality_document

    return DefaultPetPersonalityRead(document=get_default_pet_personality_document())


@router.get("/projects", response_model=list[PetProjectRead])
async def list_projects(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[PetProjectRead]:
    _, wid = await _active_workspace_id(user_id, db)
    async with db.session() as session:
        if session_dialect_name(session) == "sqlite":
            u_txt = await sqlite_parent_id_text(session, "users", user_id)
            w_txt = await sqlite_parent_id_text(session, "workspaces", wid)
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT id, user_id, workspace_id, name, description, settings,
                               created_at, updated_at
                        FROM pet_projects
                        WHERE CAST(user_id AS TEXT) = :uid
                          AND CAST(workspace_id AS TEXT) = :wid
                          AND is_deleted = 0
                        ORDER BY updated_at DESC
                        """
                    ),
                    {"uid": u_txt, "wid": w_txt},
                )
            ).mappings().all()
            return [
                PetProjectRead(
                    id=parse_uuid_stored(str(r["id"])),
                    user_id=parse_uuid_stored(str(r["user_id"])),
                    workspace_id=(
                        parse_uuid_stored(str(r["workspace_id"]))
                        if r["workspace_id"] is not None
                        else None
                    ),
                    name=r["name"],
                    description=r["description"],
                    settings=r["settings"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

        stmt = (
            select(PetProject)
            .where(
                PetProject.user_id == user_id,
                PetProject.workspace_id == wid,
                PetProject.is_deleted == False,  # noqa: E712
            )
            .order_by(col(PetProject.updated_at).desc())
        )
        rows = list((await session.exec(stmt)).all())
        return [
            PetProjectRead(
                id=r.id,
                user_id=r.user_id,
                workspace_id=r.workspace_id,
                name=r.name,
                description=r.description,
                settings=r.settings,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]


@router.post("/projects", response_model=PetProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: PetProjectCreate,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> PetProjectRead:
    _, wid = await _active_workspace_id(user_id, db)
    async with db.session() as session:
        if session_dialect_name(session) == "sqlite":
            project_id = uuid4()
            now = datetime.utcnow()
            u_txt = await sqlite_parent_id_text(session, "users", user_id)
            w_txt = await sqlite_parent_id_text(session, "workspaces", wid)
            await session.execute(
                text(
                    """
                    INSERT INTO pet_projects
                        (is_deleted, deleted_at, created_at, updated_at, id,
                         user_id, workspace_id, name, description, settings)
                    VALUES
                        (0, NULL, :created_at, :updated_at, :id,
                         :user_id, :workspace_id, :name, :description, NULL)
                    """
                ),
                {
                    "created_at": now,
                    "updated_at": now,
                    "id": project_id.hex,
                    "user_id": u_txt,
                    "workspace_id": w_txt,
                    "name": body.name,
                    "description": body.description,
                },
            )
            await session.flush()
            return PetProjectRead(
                id=project_id,
                user_id=user_id,
                workspace_id=wid,
                name=body.name,
                description=body.description,
                settings=None,
                created_at=now,
                updated_at=now,
            )

        proj = PetProject(
            user_id=user_id,
            workspace_id=wid,
            name=body.name,
            description=body.description,
        )
        session.add(proj)
        await session.flush()
        await session.refresh(proj)
        return PetProjectRead(
            id=proj.id,
            user_id=proj.user_id,
            workspace_id=proj.workspace_id,
            name=proj.name,
            description=proj.description,
            settings=proj.settings,
            created_at=proj.created_at,
            updated_at=proj.updated_at,
        )


@router.patch("/projects/{project_id}", response_model=PetProjectRead)
async def update_project(
    project_id: UUID,
    body: PetProjectUpdate,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> PetProjectRead:
    await _require_project(project_id, user_id, db)
    async with db.session() as session:
        if session_dialect_name(session) == "sqlite":
            p_txt = await sqlite_parent_id_text(session, "pet_projects", project_id)
            now = datetime.utcnow()
            sets: list[str] = ["updated_at = :now"]
            params: dict[str, Any] = {"p": p_txt, "now": now}
            if body.name is not None:
                sets.append("name = :name")
                params["name"] = body.name
            if body.description is not None:
                sets.append("description = :desc")
                params["desc"] = body.description
            if body.settings is not None:
                sets.append("settings = :settings")
                params["settings"] = body.settings
            await session.execute(
                text(f"UPDATE pet_projects SET {', '.join(sets)} WHERE CAST(id AS TEXT) = :p"),
                params,
            )
            await session.flush()
            r = await session.execute(
                text(
                    """
                    SELECT id, user_id, workspace_id, name, description, settings, created_at, updated_at
                    FROM pet_projects WHERE CAST(id AS TEXT) = :p
                    """
                ),
                {"p": p_txt},
            )
            row = r.mappings().one()
            return PetProjectRead(
                id=parse_uuid_stored(str(row["id"])),
                user_id=parse_uuid_stored(str(row["user_id"])),
                workspace_id=(
                    parse_uuid_stored(str(row["workspace_id"]))
                    if row["workspace_id"] is not None
                    else None
                ),
                name=row["name"],
                description=row["description"],
                settings=row["settings"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

        proj = await load_entity_by_id(
            session, PetProject, project_id, parent_table="pet_projects"
        )
        assert proj is not None
        if body.name is not None:
            proj.name = body.name
        if body.description is not None:
            proj.description = body.description
        if body.settings is not None:
            proj.settings = body.settings
        session.add(proj)
        await session.flush()
        await session.refresh(proj)
        return PetProjectRead(
            id=proj.id,
            user_id=proj.user_id,
            workspace_id=proj.workspace_id,
            name=proj.name,
            description=proj.description,
            settings=proj.settings,
            created_at=proj.created_at,
            updated_at=proj.updated_at,
        )


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> None:
    await _require_project(project_id, user_id, db)
    async with db.session() as session:
        if session_dialect_name(session) == "sqlite":
            p_txt = await sqlite_parent_id_text(session, "pet_projects", project_id)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            await session.execute(
                text(
                    "UPDATE pet_projects SET is_deleted = 1, deleted_at = :d, updated_at = :d "
                    "WHERE CAST(id AS TEXT) = :p"
                ),
                {"p": p_txt, "d": now},
            )
            return
        proj = await load_entity_by_id(
            session, PetProject, project_id, parent_table="pet_projects"
        )
        if proj is None:
            return
        proj.is_deleted = True
        proj.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.add(proj)


@router.get("/projects/{project_id}/files", response_model=list[PetProjectFileRead])
async def list_project_files(
    project_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[PetProjectFileRead]:
    await _require_project(project_id, user_id, db)
    async with db.session() as session:
        out: list[PetProjectFileRead] = []
        if session_dialect_name(session) == "sqlite":
            p_txt = await sqlite_parent_id_text(session, "pet_projects", project_id)
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT pf.id AS link_id, pf.pet_project_id, pf.file_id, pf.created_at AS link_created,
                               f.original_name, f.mime_type, f.size, f.is_deleted AS file_deleted
                        FROM pet_project_files pf
                        JOIN files f
                          ON lower(replace(CAST(f.id AS TEXT), '-', '')) =
                             lower(replace(CAST(pf.file_id AS TEXT), '-', ''))
                        WHERE CAST(pf.pet_project_id AS TEXT) = :p
                        ORDER BY pf.created_at DESC
                        """
                    ),
                    {"p": p_txt},
                )
            ).mappings().all()
            for r in rows:
                if r["file_deleted"]:
                    continue
                out.append(
                    PetProjectFileRead(
                        id=parse_uuid_stored(str(r["link_id"])),
                        pet_project_id=parse_uuid_stored(str(r["pet_project_id"])),
                        file_id=parse_uuid_stored(str(r["file_id"])),
                        original_name=str(r["original_name"]),
                        mime_type=r["mime_type"],
                        size=int(r["size"]),
                        created_at=r["link_created"],
                    )
                )
            return out

        stmt = (
            select(PetProjectFile)
            .where(PetProjectFile.pet_project_id == project_id)
            .order_by(col(PetProjectFile.created_at).desc())
        )
        links = list((await session.exec(stmt)).all())
        for link in links:
            f = await load_entity_by_id(
                session, FileModel, link.file_id, parent_table="files"
            )
            if f is None or f.is_deleted:
                continue
            out.append(
                PetProjectFileRead(
                    id=link.id,
                    pet_project_id=link.pet_project_id,
                    file_id=f.id,
                    original_name=f.original_name,
                    mime_type=f.mime_type,
                    size=f.size,
                    created_at=link.created_at,
                )
            )
        return out


@router.post("/projects/{project_id}/upload", response_model=FileUploadResponse)
async def upload_project_file(
    project_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    file: UploadFile = File(...),
) -> FileUploadResponse:
    proj = await _require_project(project_id, user_id, db)
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    try:
        db_file = await persist_pet_space_file(
            file,
            user_id,
            db,
            workspace_id=proj.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async with db.session() as session:
        if session_dialect_name(session) == "sqlite":
            p_txt = await sqlite_parent_id_text(session, "pet_projects", project_id)
            f_txt = await sqlite_parent_id_text(session, "files", db_file.id)
            link_id = uuid4()
            await session.execute(
                text(
                    """
                    INSERT INTO pet_project_files (id, pet_project_id, file_id, created_at)
                    VALUES (:lid, :pid, :fid, :created)
                    """
                ),
                {
                    "lid": link_id.hex,
                    "pid": p_txt,
                    "fid": f_txt,
                    "created": datetime.utcnow(),
                },
            )
        else:
            link = PetProjectFile(pet_project_id=project_id, file_id=db_file.id)
            session.add(link)
        await session.flush()

    return FileUploadResponse(
        id=db_file.id,
        name=db_file.name,
        original_name=db_file.original_name,
        file_type=db_file.file_type,
        mime_type=db_file.mime_type,
        size=db_file.size,
        checksum=db_file.checksum or "",
    )
