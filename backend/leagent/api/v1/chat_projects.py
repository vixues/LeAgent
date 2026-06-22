"""Chat project API for grouping password-protected conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from leagent.api.v1.chat_deps import ChatSvc
from leagent.db import DatabaseService, get_database_service
from leagent.services.auth import CurrentUserId
from leagent.services.chat.projects import ChatProjectReadModel, ChatProjectService

router = APIRouter()


class ChatProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    design_context: str | None = Field(default=None, max_length=50000)
    settings: str | None = Field(default=None, max_length=20000)
    password: str | None = Field(default=None, min_length=1, max_length=256)


class ChatProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    design_context: str | None = Field(default=None, max_length=50000)
    settings: str | None = Field(default=None, max_length=20000)
    password: str | None = Field(default=None, min_length=1, max_length=256)
    clear_password: bool = False


class ChatProjectRead(BaseModel):
    id: UUID
    user_id: UUID
    workspace_id: UUID | None
    name: str
    description: str | None
    design_context: str | None = None
    settings: str | None = None
    has_password: bool
    is_locked: bool
    session_count: int
    created_at: datetime
    updated_at: datetime


class ChatProjectUnlockRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChatProjectUnlockResponse(BaseModel):
    project_id: UUID
    token: str
    expires_at: int


class MoveSessionRequest(BaseModel):
    session_id: UUID
    target_project_id: UUID | None = None


class MoveSessionResponse(BaseModel):
    session_id: UUID
    project_id: UUID | None


def _project_service(db: DatabaseService) -> ChatProjectService:
    return ChatProjectService(db)


def _read(
    model: ChatProjectReadModel,
    *,
    unlocked: bool = False,
    include_protected_detail: bool = False,
) -> ChatProjectRead:
    is_locked = model.has_password and not unlocked
    return ChatProjectRead(
        id=model.id,
        user_id=model.user_id,
        workspace_id=model.workspace_id,
        name=model.name,
        description=model.description,
        design_context=model.design_context if include_protected_detail or not is_locked else None,
        settings=model.settings if include_protected_detail or not is_locked else None,
        has_password=model.has_password,
        is_locked=is_locked,
        session_count=model.session_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _project_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _project_locked() -> HTTPException:
    return HTTPException(status_code=status.HTTP_423_LOCKED, detail="Project locked")


@router.get("", response_model=list[ChatProjectRead])
async def list_chat_projects(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[ChatProjectRead]:
    service = _project_service(db)
    projects = await service.list_projects(user_id)
    return [_read(p, include_protected_detail=False) for p in projects]


@router.post("", response_model=ChatProjectRead, status_code=status.HTTP_201_CREATED)
async def create_chat_project(
    body: ChatProjectCreate,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> ChatProjectRead:
    service = _project_service(db)
    project = await service.create_project(
        user_id=user_id,
        name=body.name.strip(),
        description=body.description,
        design_context=body.design_context,
        settings=body.settings,
        password=body.password,
    )
    read = await service.get_project_read(project.id, user_id=user_id)
    if read is None:
        raise _project_not_found()
    return _read(read, unlocked=not bool(body.password), include_protected_detail=True)


@router.get("/{project_id}", response_model=ChatProjectRead)
async def get_chat_project(
    project_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    x_chat_project_token: str | None = Header(default=None, alias="X-Chat-Project-Token"),
) -> ChatProjectRead:
    service = _project_service(db)
    project = await service.get_project_read(project_id, user_id=user_id)
    if project is None:
        raise _project_not_found()
    unlocked = (not project.has_password) or service.verify_unlock_token(
        x_chat_project_token,
        project_id=project_id,
        user_id=user_id,
    )
    if project.has_password and not unlocked:
        raise _project_locked()
    return _read(project, unlocked=unlocked, include_protected_detail=True)


@router.patch("/{project_id}", response_model=ChatProjectRead)
async def update_chat_project(
    project_id: UUID,
    body: ChatProjectUpdate,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> ChatProjectRead:
    service = _project_service(db)
    project = await service.update_project(
        project_id,
        user_id=user_id,
        name=body.name.strip() if body.name is not None else None,
        description=body.description,
        design_context=body.design_context,
        settings=body.settings,
        password=body.password,
        clear_password=body.clear_password,
    )
    if project is None:
        raise _project_not_found()
    read = await service.get_project_read(project.id, user_id=user_id)
    if read is None:
        raise _project_not_found()
    return _read(read, unlocked=not read.has_password, include_protected_detail=True)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_project(
    project_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> None:
    service = _project_service(db)
    if not await service.delete_project(project_id, user_id=user_id):
        raise _project_not_found()


@router.post("/{project_id}/unlock", response_model=ChatProjectUnlockResponse)
async def unlock_chat_project(
    project_id: UUID,
    body: ChatProjectUnlockRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> ChatProjectUnlockResponse:
    service = _project_service(db)
    if not await service.verify_project_password(
        project_id,
        user_id=user_id,
        password=body.password,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    token, expires_at = service.mint_unlock_token(project_id=project_id, user_id=user_id)
    return ChatProjectUnlockResponse(project_id=project_id, token=token, expires_at=expires_at)


@router.post("/{project_id}/sessions/move", response_model=MoveSessionResponse)
async def move_session_into_project(
    project_id: UUID,
    body: MoveSessionRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    x_chat_project_token: str | None = Header(default=None, alias="X-Chat-Project-Token"),
) -> MoveSessionResponse:
    service = _project_service(db)
    target_id = body.target_project_id if body.target_project_id is not None else project_id
    try:
        await service.require_project_access(
            target_id,
            user_id=user_id,
            unlock_token=x_chat_project_token,
        )
    except PermissionError as exc:
        if str(exc) == "Project locked":
            raise _project_locked() from exc
        raise _project_not_found() from exc
    session = await chat_svc.move_session_to_project(
        body.session_id,
        user_id=user_id,
        project_id=target_id,
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return MoveSessionResponse(session_id=session.id, project_id=session.project_id)
