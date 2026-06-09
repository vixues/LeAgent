"""Document management API endpoints."""

from __future__ import annotations

import os
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlmodel import col, func, select

from leagent.config.settings import get_settings
from leagent.file.primitives import classify_file_kind
from leagent.schema.api import PaginatedResponse
from leagent.services.auth import CurrentUserId
from leagent.db import DatabaseService, get_database_service
from leagent.db.models import (
    ChatSession,
    File as FileModel,
    FileRead,
    FileStatus,
    FileType,
    PetProject,
    PetProjectFile,
)

router = APIRouter()


def _pet_project_library_file_ids_subquery(user_id: UUID):
    """File IDs linked to Pet Space projects — excluded from knowledge document lists."""
    return (
        select(PetProjectFile.file_id)
        .join(PetProject, PetProjectFile.pet_project_id == PetProject.id)
        .where(
            PetProject.user_id == user_id,
            PetProject.is_deleted == False,  # noqa: E712
        )
    )


def _legacy_knowledge_documents_dir() -> str:
    """Previous default blob directory (still indexed for existing installs)."""
    return os.path.join(get_settings().files.resolved_knowledge_storage_dir(), "documents")


def _system_knowledge_blob_dir() -> str:
    """Dedicated on-disk folder for system knowledge base documents."""
    return os.path.join(get_settings().files.resolved_knowledge_storage_dir(), "system")


def _knowledge_storage_roots_norm() -> tuple[str, ...]:
    """Normalized absolute dirs that count as system knowledge storage."""
    return (
        os.path.normpath(_system_knowledge_blob_dir()),
        os.path.normpath(_legacy_knowledge_documents_dir()),
    )


def _is_system_knowledge_storage_path(storage_path: str | None) -> bool:
    """True when *storage_path* lives under the system knowledge blob dirs."""
    if not storage_path:
        return False
    nf = os.path.normpath(storage_path)
    for root in _knowledge_storage_roots_norm():
        if nf == root or nf.startswith(root + os.sep):
            return True
    return False


def _storage_path_under_system_knowledge_sql():
    """SQLModel/SQLAlchemy filter: ``storage_path`` under system knowledge roots."""
    parts: list[Any] = []
    for root in _knowledge_storage_roots_norm():
        parts.append(FileModel.storage_path == root)
        parts.append(FileModel.storage_path.startswith(root + os.sep))
    return or_(*parts)


def _upload_dir() -> str:
    """Return the canonical directory for new knowledge uploads (``…/knowledge/system``)."""
    return _system_knowledge_blob_dir()


MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_PROMOTE_FILES = 50

_FILE_KIND_TO_TYPE = {
    "image": FileType.IMAGE,
    "document": FileType.DOCUMENT,
    "data": FileType.DATA,
    "audio": FileType.AUDIO,
    "video": FileType.VIDEO,
    "archive": FileType.ARCHIVE,
    "code": FileType.CODE,
    "text": FileType.DOCUMENT,
}


class DocumentUploadResponse(BaseModel):
    """Response for document upload."""

    id: UUID
    name: str
    original_name: str
    file_type: FileType
    mime_type: Optional[str]
    size: int
    status: FileStatus


class DocumentSearchRequest(BaseModel):
    """Request schema for document search."""

    query: str = Field(..., min_length=1, max_length=1000)
    file_types: Optional[list[FileType]] = None
    folder_id: Optional[UUID] = None
    limit: int = Field(default=10, ge=1, le=100)


class DocumentSearchResult(BaseModel):
    """Search result for a document."""

    id: UUID
    name: str
    file_type: FileType
    score: float
    snippet: Optional[str] = None


class DocumentSearchResponse(BaseModel):
    """Response for document search."""

    query: str
    results: list[DocumentSearchResult]
    total: int


class PromoteToKnowledgeRequest(BaseModel):
    """Copy session/workspace files into the system knowledge store."""

    file_ids: list[UUID] = Field(..., min_length=1, max_length=MAX_PROMOTE_FILES)
    session_id: UUID = Field(
        ...,
        description="Knowledge-base chat session id (shared catalog session).",
    )


class SkippedPromoteFile(BaseModel):
    """A source file that was not copied into the knowledge store."""

    id: UUID
    reason: str


class PromoteToKnowledgeResponse(BaseModel):
    """Result of promoting files into the system knowledge base."""

    promoted: list[DocumentUploadResponse]
    skipped: list[SkippedPromoteFile]


def get_file_type(mime_type: str | None, filename: str | None = None) -> FileType:
    """Determine :class:`FileType` via the canonical :func:`classify_file_kind`."""
    kind = classify_file_kind(filename or "", mime_type)
    return _FILE_KIND_TO_TYPE.get(kind.value, FileType.OTHER)


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    file: UploadFile = File(...),
    session_id: UUID = Form(...),
    folder_id: Optional[UUID] = Form(default=None),
    process_ocr: bool = Form(default=True),
    index_for_search: bool = Form(default=True),
) -> DocumentUploadResponse:
    """Upload a document for processing and indexing.

    Since every :class:`FileModel` row now lives inside a chat session,
    document uploads are scoped to the session the user is currently
    viewing. Callers that need a session-less document repository should
    create a dedicated "documents" session and reuse its id.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    content = await file.read()
    file_size = len(content)

    from leagent.api.v1.files import _store_blob

    ref = await _store_blob(
        content,
        filename=file.filename,
        content_type=file.content_type,
        user_id=user_id,
        session_id=session_id,
    )
    file_id = ref.id
    safe_name = os.path.basename(ref.storage_key)
    storage_path = ref.metadata.get("storage_path", ref.storage_key)
    checksum = ref.checksum

    file_type = get_file_type(file.content_type, file.filename)

    async with db.session() as session:
        db_file = FileModel(
            id=file_id,
            session_id=session_id,
            name=safe_name,
            original_name=file.filename,
            file_type=file_type,
            mime_type=file.content_type,
            size=file_size,
            status=FileStatus.UPLOADED,
            user_id=user_id,
            folder_id=folder_id,
            storage_path=storage_path,
            checksum=checksum,
        )
        session.add(db_file)
        await session.flush()
        await session.refresh(db_file)

        return DocumentUploadResponse(
            id=db_file.id,
            name=db_file.name,
            original_name=db_file.original_name,
            file_type=db_file.file_type,
            mime_type=db_file.mime_type,
            size=db_file.size,
            status=db_file.status,
        )


@router.post("/promote", response_model=PromoteToKnowledgeResponse)
async def promote_to_knowledge(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    body: PromoteToKnowledgeRequest,
) -> PromoteToKnowledgeResponse:
    """Copy owned chat/workspace files into the system knowledge directory.

    Does not move or delete the source rows; creates new :class:`FileModel` rows
    under ``…/knowledge/system/`` (and schedules the same post-processing as
    chat uploads). Sources that already live in the system knowledge store are
    skipped.
    """
    from leagent.tasks.jobs import enqueue_file_processing  # noqa: PLC0415

    promoted: list[DocumentUploadResponse] = []
    skipped: list[SkippedPromoteFile] = []

    async with db.session() as session:
        cs = await session.get(ChatSession, body.session_id)
        if cs is None or cs.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid session_id for the current user",
            )

    for raw_id in body.file_ids:
        async with db.session() as session:
            src = await session.get(FileModel, raw_id)
            if src is None or src.is_deleted:
                skipped.append(
                    SkippedPromoteFile(id=raw_id, reason="not_found")
                )
                continue
            if src.user_id != user_id:
                skipped.append(
                    SkippedPromoteFile(id=raw_id, reason="forbidden")
                )
                continue
            if _is_system_knowledge_storage_path(src.storage_path):
                skipped.append(
                    SkippedPromoteFile(id=raw_id, reason="already_in_knowledge")
                )
                continue
            if not src.storage_path or not os.path.isfile(src.storage_path):
                skipped.append(
                    SkippedPromoteFile(id=raw_id, reason="missing_on_disk")
                )
                continue
            if src.size > MAX_FILE_SIZE:
                skipped.append(
                    SkippedPromoteFile(id=raw_id, reason="too_large")
                )
                continue

            with open(src.storage_path, "rb") as rf:
                content = rf.read()

            from leagent.api.v1.files import _store_blob

            ref = await _store_blob(
                content,
                filename=src.original_name,
                content_type=src.mime_type,
                user_id=user_id,
                session_id=body.session_id,
            )
            file_id = ref.id
            safe_name = os.path.basename(ref.storage_key)
            storage_path = ref.metadata.get("storage_path", ref.storage_key)
            checksum = ref.checksum

            db_new = FileModel(
                id=file_id,
                session_id=body.session_id,
                name=safe_name,
                original_name=src.original_name,
                file_type=src.file_type,
                mime_type=src.mime_type,
                size=len(content),
                status=FileStatus.UPLOADED,
                user_id=user_id,
                folder_id=src.folder_id,
                storage_path=storage_path,
                checksum=checksum,
            )
            session.add(db_new)
            await session.flush()
            await session.refresh(db_new)

            promoted.append(
                DocumentUploadResponse(
                    id=db_new.id,
                    name=db_new.name,
                    original_name=db_new.original_name,
                    file_type=db_new.file_type,
                    mime_type=db_new.mime_type,
                    size=db_new.size,
                    status=db_new.status,
                )
            )

            await enqueue_file_processing(
                db,
                file_id=str(file_id),
                storage_path=storage_path,
                mime_type=db_new.mime_type,
                original_name=db_new.original_name,
                user_id=user_id,
            )

    return PromoteToKnowledgeResponse(promoted=promoted, skipped=skipped)


@router.get("", response_model=PaginatedResponse[FileRead])
async def list_documents(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    file_type: Optional[FileType] = Query(default=None),
    status: Optional[FileStatus] = Query(default=None),
    folder_id: Optional[UUID] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
) -> PaginatedResponse[FileRead]:
    """List documents for the current user with pagination and filters."""
    async with db.session() as session:
        pet_lib = _pet_project_library_file_ids_subquery(user_id)
        query = select(FileModel).where(
            FileModel.user_id == user_id,
            FileModel.is_deleted == False,
            ~FileModel.id.in_(pet_lib),
            _storage_path_under_system_knowledge_sql(),
        )

        if file_type is not None:
            query = query.where(FileModel.file_type == file_type)
        if status is not None:
            query = query.where(FileModel.status == status)
        if folder_id is not None:
            query = query.where(FileModel.folder_id == folder_id)
        if search:
            query = query.where(FileModel.original_name.ilike(f"%{search}%"))

        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.exec(count_query)
        total = count_result.one()

        query = query.order_by(col(FileModel.created_at).desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.exec(query)
        files = list(result.all())

        return PaginatedResponse[FileRead](
            items=[FileRead.model_validate(f) for f in files],
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
            has_prev=page > 1,
        )


@router.get("/search", response_model=DocumentSearchResponse)
async def search_documents(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    query: str = Query(..., min_length=1, max_length=1000),
    file_types: Optional[str] = Query(default=None, description="Comma-separated file types"),
    folder_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> DocumentSearchResponse:
    """Perform semantic search across indexed documents.

    This is a placeholder implementation that performs text-based search.
    In production, this would integrate with a vector database for semantic search.
    """
    async with db.session() as session:
        pet_lib = _pet_project_library_file_ids_subquery(user_id)
        db_query = select(FileModel).where(
            FileModel.user_id == user_id,
            FileModel.is_deleted == False,
            FileModel.is_indexed == True,
            ~FileModel.id.in_(pet_lib),
            _storage_path_under_system_knowledge_sql(),
        )

        if file_types:
            type_list = [FileType(t.strip()) for t in file_types.split(",") if t.strip()]
            if type_list:
                db_query = db_query.where(FileModel.file_type.in_(type_list))

        if folder_id is not None:
            db_query = db_query.where(FileModel.folder_id == folder_id)

        db_query = db_query.where(
            (FileModel.original_name.ilike(f"%{query}%"))
            | (FileModel.extracted_text.ilike(f"%{query}%"))
        )

        db_query = db_query.limit(limit)

        result = await session.exec(db_query)
        files = list(result.all())

        search_results = []
        for f in files:
            snippet = None
            if f.extracted_text:
                query_lower = query.lower()
                text_lower = f.extracted_text.lower()
                idx = text_lower.find(query_lower)
                if idx >= 0:
                    start = max(0, idx - 50)
                    end = min(len(f.extracted_text), idx + len(query) + 50)
                    snippet = f.extracted_text[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(f.extracted_text):
                        snippet = snippet + "..."

            search_results.append(
                DocumentSearchResult(
                    id=f.id,
                    name=f.original_name,
                    file_type=f.file_type,
                    score=1.0,
                    snippet=snippet,
                )
            )

        return DocumentSearchResponse(
            query=query,
            results=search_results,
            total=len(search_results),
        )
