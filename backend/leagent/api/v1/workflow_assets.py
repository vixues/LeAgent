"""Workflow asset library (non-chat) — upload + list.

Purpose: allow the ComfyUI-style workflow editor to pick/upload images and other
assets without relying on a chat session id.

These assets are stored as managed files (``files`` table) with ``session_id IS NULL``.
We tag them via ``file_metadata`` so they can be listed separately from other
non-chat libraries (e.g. Pet Space).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import select

from leagent.services.auth import CurrentUserId
from leagent.db import DatabaseService, get_database_service
from leagent.db.models.file import File as FileModel

router = APIRouter()

_WORKFLOW_LIBRARY_TAG = '"library": "workflow"'


class WorkflowAssetItem(BaseModel):
    id: UUID
    filename: str
    mime_type: str | None = None
    size: int = 0
    preview_url: str
    download_url: str


class WorkflowAssetListResponse(BaseModel):
    assets: list[WorkflowAssetItem]


class WorkflowAssetUploadResponse(BaseModel):
    id: UUID
    filename: str
    mime_type: str | None = None
    size: int = 0


@router.get("/assets", response_model=WorkflowAssetListResponse)
async def list_workflow_assets(
    user_id: CurrentUserId,
    db: DatabaseService = Depends(get_database_service),
) -> WorkflowAssetListResponse:
    async with db.session() as session:
        result = await session.exec(
            select(FileModel)
            .where(FileModel.user_id == user_id)
            .where(FileModel.session_id.is_(None))
            .where(FileModel.is_deleted == False)  # noqa: E712
            .where(FileModel.file_metadata.like(f"%{_WORKFLOW_LIBRARY_TAG}%"))
            .order_by(FileModel.created_at.desc())
        )
        rows = list(result.all())

    assets: list[WorkflowAssetItem] = []
    for row in rows:
        assets.append(
            WorkflowAssetItem(
                id=row.id,
                filename=row.original_name or row.name,
                mime_type=row.mime_type,
                size=row.size or 0,
                preview_url=f"/api/v1/files/{row.id}/preview",
                download_url=f"/api/v1/files/{row.id}/download",
            )
        )
    return WorkflowAssetListResponse(assets=assets)


@router.post("/assets/upload", response_model=WorkflowAssetUploadResponse)
async def upload_workflow_asset(
    user_id: CurrentUserId,
    db: DatabaseService = Depends(get_database_service),
    file: UploadFile = File(...),
) -> WorkflowAssetUploadResponse:
    """Upload an asset into the workflow library (no chat session required)."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Reuse the existing non-chat persistence path (Pet Space) which stores
    # ``session_id IS NULL``.
    from leagent.api.v1.files import persist_pet_space_file

    try:
        db_file = await persist_pet_space_file(file, user_id, db, workspace_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Tag as workflow library for listing.
    async with db.session() as session:
        row = await session.get(FileModel, db_file.id)
        if row is not None and row.user_id == user_id:
            meta: dict[str, Any] = {}
            try:
                if row.file_metadata:
                    meta = json.loads(row.file_metadata) if isinstance(row.file_metadata, str) else {}
            except Exception:  # noqa: BLE001
                meta = {}
            meta["library"] = "workflow"
            row.file_metadata = json.dumps(meta, ensure_ascii=False)
            session.add(row)

    return WorkflowAssetUploadResponse(
        id=db_file.id,
        filename=db_file.original_name or db_file.name,
        mime_type=db_file.mime_type,
        size=db_file.size or 0,
    )

