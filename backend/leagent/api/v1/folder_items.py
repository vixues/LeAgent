"""Folder-item association management API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import select

from leagent.services.auth import CurrentUserId
from leagent.db import DatabaseService, get_database_service
from leagent.db.sqlite_compat import load_entity_by_id
from leagent.db.models.file import File
from leagent.db.models.folder import Folder

router = APIRouter()


class FolderItemResponse(BaseModel):
    file_id: UUID
    folder_id: UUID
    file_name: str
    file_type: str
    size: int
    mime_type: Optional[str] = None


class AddItemRequest(BaseModel):
    file_id: UUID
    folder_id: UUID


class MoveItemRequest(BaseModel):
    to_folder_id: UUID


class ReorderRequest(BaseModel):
    file_ids: list[UUID]


@router.get("", response_model=list[FolderItemResponse])
async def list_folder_items(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[FolderItemResponse]:
    """List all files in a folder."""
    async with db.session() as session:
        stmt = (
            select(File)
            .where(File.folder_id == folder_id)
            .where(File.is_deleted == False)  # noqa: E712
        )
        result = await session.exec(stmt)
        files = result.all()

        return [
            FolderItemResponse(
                file_id=f.id,
                folder_id=folder_id,
                file_name=f.original_name,
                file_type=f.file_type.value,
                size=f.size,
                mime_type=f.mime_type,
            )
            for f in files
        ]


@router.post("", response_model=FolderItemResponse, status_code=status.HTTP_201_CREATED)
async def add_item_to_folder(
    data: AddItemRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FolderItemResponse:
    """Add a file to a folder."""
    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, data.folder_id, parent_table="folders")
        if not folder or folder.is_deleted:
            raise HTTPException(status_code=404, detail="Folder not found")

        f = await load_entity_by_id(session, File, data.file_id, parent_table="files")
        if not f or f.is_deleted:
            raise HTTPException(status_code=404, detail="File not found")

        f.folder_id = data.folder_id
        f.updated_at = datetime.utcnow()
        session.add(f)

        folder.file_count = folder.file_count + 1
        session.add(folder)

        return FolderItemResponse(
            file_id=f.id,
            folder_id=data.folder_id,
            file_name=f.original_name,
            file_type=f.file_type.value,
            size=f.size,
            mime_type=f.mime_type,
        )


@router.delete("/{folder_id}/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_folder(
    folder_id: UUID,
    file_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> None:
    """Remove a file from a folder (unlink, not delete)."""
    async with db.session() as session:
        f = await load_entity_by_id(session, File, file_id, parent_table="files")
        if not f or f.is_deleted:
            raise HTTPException(status_code=404, detail="File not found")

        if f.folder_id != folder_id:
            raise HTTPException(status_code=400, detail="File is not in this folder")

        f.folder_id = None
        f.updated_at = datetime.utcnow()
        session.add(f)

        folder = await load_entity_by_id(session, Folder, folder_id, parent_table="folders")
        if folder and folder.file_count > 0:
            folder.file_count = folder.file_count - 1
            session.add(folder)


@router.put("/{file_id}/move")
async def move_item(
    file_id: UUID,
    data: MoveItemRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Move a file to a different folder."""
    async with db.session() as session:
        f = await load_entity_by_id(session, File, file_id, parent_table="files")
        if not f or f.is_deleted:
            raise HTTPException(status_code=404, detail="File not found")

        target = await load_entity_by_id(session, Folder, data.to_folder_id, parent_table="folders")
        if not target or target.is_deleted:
            raise HTTPException(status_code=404, detail="Target folder not found")

        old_folder_id = f.folder_id
        f.folder_id = data.to_folder_id
        f.updated_at = datetime.utcnow()
        session.add(f)

        if old_folder_id:
            old_folder = await load_entity_by_id(session, Folder, old_folder_id, parent_table="folders")
            if old_folder and old_folder.file_count > 0:
                old_folder.file_count -= 1
                session.add(old_folder)

        target.file_count += 1
        session.add(target)

        return {
            "file_id": str(file_id),
            "from_folder_id": str(old_folder_id) if old_folder_id else None,
            "to_folder_id": str(data.to_folder_id),
        }
