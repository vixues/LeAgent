"""File operations API endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import mimetypes
import os
import re
import tempfile
import zipfile
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import text
from sqlmodel import select
from starlette.background import BackgroundTask

from leagent.config.constants import MAX_UPLOAD_SIZE_BYTES
from leagent.config.settings import get_settings
from leagent.file.primitives import classify_file_kind
from leagent.services.auth import (
    CurrentUserId,
    OptionalUserId,
    SignedUrlError,
    verify_signed_token,
)
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.models import (
    File as FileModel,
)
from leagent.services.database.models import (
    FileRead,
    FileStatus,
    FileType,
)
from leagent.services.database.sqlite_compat import (
    file_model_from_sqlite_row,
    same_user_id,
    sqlite_parent_id_text,
)
from leagent.services.database.sqlite_compat import session_dialect_name as _session_dialect_name
from leagent.services.session.paths import get_session_path_registry

_logger = logging.getLogger(__name__)

router = APIRouter()


def _upload_dir() -> str:
    """Return the canonical on-disk upload directory."""
    return get_settings().files.upload_dir


MAX_FILE_SIZE = MAX_UPLOAD_SIZE_BYTES

# Multi-file ZIP download (POST /files/bundle/download)
MAX_BUNDLE_FILE_COUNT = 80
MAX_BUNDLE_TOTAL_BYTES = 400 * 1024 * 1024  # 400 MB uncompressed sum (guardrail)


def resolve_pet_space_upload_mime_type(
    filename: str | None,
    declared: str | None,
    content: bytes,
) -> str | None:
    """Infer a useful MIME for Pet Space uploads when the client sends a weak ``Content-Type``.

    Browsers sometimes upload SVG/GIF/PNG as ``application/octet-stream``; Pet Space uses MIME to
    decide whether a file can be shown as a pet appearance in the dock.
    """
    d = (declared or "").strip() or None
    if d and d != "application/octet-stream":
        return d
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    if len(content) >= 6 and content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    head = content[:8192].lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<svg") or b"<svg" in content[:8192]:
        return "image/svg+xml"
    return d


class FileBundleDownloadRequest(BaseModel):
    """Request body for zipping multiple owned files into one archive."""

    file_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=MAX_BUNDLE_FILE_COUNT,
        description="File UUIDs to include (order preserved; duplicates removed).",
    )
    filename: str | None = Field(
        default=None,
        max_length=200,
        description="Suggested download name; must end in .zip after sanitization.",
    )


def _sanitize_bundle_download_filename(raw: str | None) -> str:
    """Return a safe single-segment ``*.zip`` filename for Content-Disposition."""
    base = (raw or "workspace-files.zip").strip() or "workspace-files.zip"
    base = os.path.basename(base.replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", base).strip("._") or "workspace-files"
    if not base.lower().endswith(".zip"):
        base = f"{base}.zip"
    return base[:180]


def _unlink_quiet(path: str) -> None:
    with contextlib.suppress(OSError):
        os.unlink(path)


class FileUploadResponse(BaseModel):
    """Response for file upload."""

    id: UUID
    name: str
    original_name: str
    file_type: FileType
    mime_type: Optional[str]
    size: int
    checksum: str


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


def get_file_type(mime_type: str | None, filename: str | None = None) -> FileType:
    """Determine :class:`FileType` via the canonical :func:`classify_file_kind`."""
    kind = classify_file_kind(filename or "", mime_type)
    return _FILE_KIND_TO_TYPE.get(kind.value, FileType.OTHER)


async def _background_process_file(file_id: str, storage_path: str, mime_type: str | None, original_name: str | None) -> None:
    """Background task to auto-process an uploaded file."""
    try:
        from leagent.services.service_manager import get_service_manager
        sm = get_service_manager()
        if sm.file_processing:
            await sm.file_processing.process_and_update_db(
                file_id=file_id,
                file_path=storage_path,
                mime_type=mime_type,
                original_name=original_name,
            )
    except Exception as exc:
        _logger.warning("Background file processing failed for %s: %s", file_id, exc)


async def persist_uploaded_file(
    upload: UploadFile,
    user_id: UUID,
    db: DatabaseService,
    *,
    session_id: UUID,
    folder_id: UUID | None = None,
    background_tasks: BackgroundTasks | None = None,
) -> FileModel:
    """Save an UploadFile to disk + DB and schedule text extraction.

    Every uploaded file now belongs to exactly one chat session — the
    :class:`FileModel` row carries a non-nullable ``session_id`` FK so the
    :class:`SessionManager` and preview endpoint can answer
    "which session owns this file?" in a single query.
    """
    if not upload.filename:
        raise ValueError("Filename is required")

    content = await upload.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large ({file_size} bytes). Maximum is {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )

    checksum = hashlib.sha256(content).hexdigest()

    upload_root = get_session_path_registry().ensure_uploads_dir(session_id)
    file_id = uuid4()
    safe_name = f"{file_id}_{upload.filename.replace('/', '_')}"
    storage_path = str(upload_root / safe_name)

    with open(storage_path, "wb") as f:
        f.write(content)

    file_type = get_file_type(upload.content_type, upload.filename)

    async with db.session() as session:
        db_file = FileModel(
            id=file_id,
            session_id=session_id,
            name=safe_name,
            original_name=upload.filename,
            file_type=file_type,
            mime_type=upload.content_type,
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

    if background_tasks is not None:
        background_tasks.add_task(
            _background_process_file,
            str(file_id),
            storage_path,
            upload.content_type,
            upload.filename,
        )
    else:
        asyncio.ensure_future(
            _background_process_file(
                str(file_id), storage_path, upload.content_type, upload.filename
            )
        )

    return db_file


async def persist_pet_space_file(
    upload: UploadFile,
    user_id: UUID,
    db: DatabaseService,
    *,
    workspace_id: Optional[UUID],
    background_tasks: BackgroundTasks | None = None,
) -> FileModel:
    """Save an upload to disk + DB for Pet Space (no chat session).

    The row has ``session_id is NULL`` and is linked via :class:`PetProjectFile`.
    """
    if not upload.filename:
        raise ValueError("Filename is required")

    content = await upload.read()
    file_size = len(content)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large ({file_size} bytes). Maximum is {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )

    checksum = hashlib.sha256(content).hexdigest()

    upload_root = _upload_dir()
    os.makedirs(upload_root, exist_ok=True)
    file_id = uuid4()
    safe_name = f"{file_id}_{upload.filename.replace('/', '_')}"
    storage_path = os.path.join(upload_root, safe_name)

    with open(storage_path, "wb") as f:
        f.write(content)

    resolved_mime = resolve_pet_space_upload_mime_type(upload.filename, upload.content_type, content)
    file_type = get_file_type(resolved_mime, upload.filename)

    async with db.session() as session:
        if _session_dialect_name(session) == "sqlite":
            u_txt = await sqlite_parent_id_text(session, "users", user_id)
            w_txt: str | None
            if workspace_id is not None:
                w_txt = await sqlite_parent_id_text(session, "workspaces", workspace_id)
            else:
                w_txt = None
            now = datetime.utcnow()
            # Store Alembic / SQLAlchemy enum *names* (IMAGE, UPLOADED), not str-Enum values (image).
            ft_val = file_type.name if isinstance(file_type, FileType) else str(file_type)
            await session.execute(
                text(
                    """
                    INSERT INTO files (
                        is_deleted, deleted_at, created_at, updated_at, id,
                        name, original_name, file_type, mime_type, size, status,
                        user_id, workspace_id, folder_id, session_id,
                        storage_path, storage_bucket, checksum,
                        extracted_text, file_metadata, page_count, has_ocr, ocr_language,
                        embedding_id, is_indexed, expires_at
                    ) VALUES (
                        0, NULL, :c1, :c2, :id,
                        :name, :oname, :ftype, :mime, :size, :status,
                        :uid, """
                    + ("NULL" if w_txt is None else ":wid")
                    + """, NULL, NULL,
                        :path, NULL, :checksum,
                        NULL, NULL, NULL, 0, NULL,
                        NULL, 0, NULL
                    )
                    """
                ),
                (
                    {
                        "c1": now,
                        "c2": now,
                        "id": file_id.hex,
                        "name": safe_name,
                        "oname": upload.filename,
                        "ftype": ft_val,
                        "mime": resolved_mime,
                        "size": file_size,
                        "status": FileStatus.UPLOADED.name,
                        "uid": u_txt,
                        "path": storage_path,
                        "checksum": checksum,
                    }
                    | ({"wid": w_txt} if w_txt is not None else {})
                ),
            )
            await session.flush()
            db_file = FileModel(
                id=file_id,
                session_id=None,
                name=safe_name,
                original_name=upload.filename,
                file_type=file_type,
                mime_type=resolved_mime,
                size=file_size,
                status=FileStatus.UPLOADED,
                user_id=user_id,
                workspace_id=workspace_id,
                folder_id=None,
                storage_path=storage_path,
                checksum=checksum,
                is_deleted=False,
                deleted_at=None,
                created_at=now,
                updated_at=now,
            )
        else:
            db_file = FileModel(
                id=file_id,
                session_id=None,
                name=safe_name,
                original_name=upload.filename,
                file_type=file_type,
                mime_type=resolved_mime,
                size=file_size,
                status=FileStatus.UPLOADED,
                user_id=user_id,
                workspace_id=workspace_id,
                folder_id=None,
                storage_path=storage_path,
                checksum=checksum,
            )
            session.add(db_file)
            await session.flush()
            await session.refresh(db_file)

    if background_tasks is not None:
        background_tasks.add_task(
            _background_process_file,
            str(file_id),
            storage_path,
            resolved_mime,
            upload.filename,
        )
    else:
        asyncio.ensure_future(
            _background_process_file(
                str(file_id), storage_path, resolved_mime, upload.filename
            )
        )

    return db_file


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session_id: UUID = Form(...),
    folder_id: Optional[UUID] = Form(default=None),
) -> FileUploadResponse:
    """Upload a file and attach it to the given chat session."""
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

    try:
        db_file = await persist_uploaded_file(
            file,
            user_id,
            db,
            session_id=session_id,
            folder_id=folder_id,
            background_tasks=background_tasks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return FileUploadResponse(
        id=db_file.id,
        name=db_file.name,
        original_name=db_file.original_name,
        file_type=db_file.file_type,
        mime_type=db_file.mime_type,
        size=db_file.size,
        checksum=db_file.checksum or "",
    )


@router.post("/bundle/download")
async def download_file_bundle(
    body: FileBundleDownloadRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FileResponse:
    """Zip multiple files the user owns into one ``.zip`` (JWT only; not signed-URL).

    Used by the workspace Files panel for compressed bulk download. For in-session
    automation the agent should use ``archive_manager`` (create/list/extract).
    """
    unique_ids = list(dict.fromkeys(body.file_ids))
    out_name = _sanitize_bundle_download_filename(body.filename)

    async with db.session() as session:
        stmt = select(FileModel).where(
            FileModel.id.in_(unique_ids),
            FileModel.user_id == user_id,
            FileModel.is_deleted == False,  # noqa: E712
        )
        result = await session.exec(stmt)
        rows = list(result.all())

    found = {f.id for f in rows}
    missing = [str(i) for i in unique_ids if i not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"One or more files were not found or not owned by you: {', '.join(missing[:8])}",
        )

    id_to_row = {f.id: f for f in rows}
    ordered = [id_to_row[i] for i in unique_ids]

    total_size = sum(max(0, f.size) for f in ordered)
    if total_size > MAX_BUNDLE_TOTAL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Combined file size ({total_size} bytes) exceeds bundle limit "
                f"({MAX_BUNDLE_TOTAL_BYTES} bytes). Download fewer files or use the agent "
                "archive_manager tool for server-side archives."
            ),
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_f:
        tmp_path = tmp_f.name

    used_arcnames: set[str] = set()
    try:
        with zipfile.ZipFile(
            tmp_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as zf:
            for f in ordered:
                if not f.storage_path or not os.path.isfile(f.storage_path):
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"File missing on storage: {f.id}",
                    )
                arc = f.original_name or f.name
                base, ext = os.path.splitext(arc)
                candidate = arc
                n = 1
                while candidate in used_arcnames:
                    candidate = f"{base}_{n}{ext}"
                    n += 1
                used_arcnames.add(candidate)
                zf.write(f.storage_path, arcname=candidate)
    except HTTPException:
        _unlink_quiet(tmp_path)
        raise
    except OSError as exc:
        _unlink_quiet(tmp_path)
        _logger.warning("bundle_zip_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not build zip archive",
        ) from exc

    return FileResponse(
        tmp_path,
        media_type="application/zip",
        filename=out_name,
        background=BackgroundTask(_unlink_quiet, tmp_path),
    )


async def _resolve_file_for_serve(
    file_id: UUID,
    *,
    token: str | None,
    jwt_user_id: UUID | None,
    required_scope: str,
    db: DatabaseService,
) -> FileModel:
    """Authorise + load a :class:`FileModel` row for download/preview.

    Two authentication paths are accepted:

    * **Signed URL** — ``?token=<signed>`` query param whose HMAC scope
      matches ``required_scope`` and whose embedded ``uid`` matches the
      file's owner. This lets ``<img src>`` / ``<object data>`` tags
      render attachments without a second round-trip for the bearer.
    * **JWT bearer** — the standard ``Authorization: Bearer`` header for
      direct API consumers.

    Returns the :class:`FileModel` row so the caller can build the
    :class:`FileResponse`. Raises :class:`HTTPException` on any auth
    failure so the endpoint shape stays flat.
    """
    settings = get_settings()
    owner_id_from_token: UUID | None = None
    if token:
        try:
            signed = verify_signed_token(settings, token)
        except SignedUrlError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
            ) from exc
        if signed.scope != required_scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Signed URL scope mismatch (want {required_scope}, got {signed.scope})",
            )
        if signed.attachment_id != file_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Signed URL does not match file id",
            )
        owner_id_from_token = signed.user_id
    elif jwt_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="File access requires either a signed URL token or a Bearer JWT",
        )

    async with db.session() as session:
        if _session_dialect_name(session) == "sqlite":
            id_txt = await sqlite_parent_id_text(session, "files", file_id)
            r = await session.execute(
                text("SELECT * FROM files WHERE CAST(id AS TEXT) = :id"),
                {"id": id_txt},
            )
            row = r.mappings().first()
            if row is None or row["is_deleted"]:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
                )
            file = file_model_from_sqlite_row(row)
        else:
            file = await session.get(FileModel, file_id)
            if not file or file.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
                )

        effective_user = owner_id_from_token or jwt_user_id
        if effective_user is not None and not same_user_id(file.user_id, effective_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this file",
            )

        if not os.path.exists(file.storage_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found on storage",
            )
        return file


_INLINE_MIME_PREFIXES = ("image/", "text/", "audio/", "video/")
_INLINE_EXTRA_MIME = {
    "application/pdf",
    "application/json",
    "application/xml",
    "application/javascript",
}


def _is_inline_safe(mime: str | None) -> bool:
    """Return ``True`` when the browser can safely render ``mime`` inline."""
    if not mime:
        return False
    if mime in _INLINE_EXTRA_MIME:
        return True
    return any(mime.startswith(p) for p in _INLINE_MIME_PREFIXES)


@router.get("/events/stream")
async def stream_file_events(
    user_id: CurrentUserId,
    request: Request,
    leagent_machine_fp: str | None = Query(default=None),
) -> EventSourceResponse:
    """Keep the SPA file-sync EventSource connected.

    File mutations are already reflected through ordinary HTTP responses and
    local browser events. This endpoint provides the server-side SSE contract
    the SPA expects, avoiding repeated 404 reconnect noise until cross-worker
    file event fan-out is introduced.
    """
    del user_id, leagent_machine_fp

    async def _gen():
        try:
            yield {"event": "ready", "data": "{}"}
            while not await request.is_disconnected():
                await asyncio.sleep(15)
                yield {"event": "heartbeat", "data": "{}"}
        except asyncio.CancelledError:
            return

    return EventSourceResponse(_gen(), media_type="text/event-stream")


@router.get("/{file_id}")
@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    user_id: OptionalUserId = None,
    token: str | None = Query(default=None),
) -> FileResponse:
    """Download a file by ID.

    Accepts either a bearer JWT or a ``?token=`` signed URL with
    ``scope=download`` (see :mod:`leagent.services.auth.signed_url`).
    """
    file = await _resolve_file_for_serve(
        file_id,
        token=token,
        jwt_user_id=user_id,
        required_scope="download",
        db=db,
    )
    return FileResponse(
        path=file.storage_path,
        filename=file.original_name,
        media_type=file.mime_type or "application/octet-stream",
    )


@router.get("/{file_id}/preview")
async def preview_file(
    file_id: UUID,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    user_id: OptionalUserId = None,
    token: str | None = Query(default=None),
) -> FileResponse:
    """Serve a session attachment inline for in-browser preview.

    Accepts either a bearer JWT or a ``?token=`` signed URL with
    ``scope=preview``. The response uses ``Content-Disposition: inline``
    and — for non-renderable MIME types — falls back to
    ``application/octet-stream`` so the browser prompts a download
    instead of leaking content to an inline viewer that can't handle
    it safely.
    """
    file = await _resolve_file_for_serve(
        file_id,
        token=token,
        jwt_user_id=user_id,
        required_scope="preview",
        db=db,
    )
    mime = file.mime_type or "application/octet-stream"
    if not _is_inline_safe(mime):
        mime = "application/octet-stream"
    headers = {
        "Cache-Control": "private, max-age=60",
    }
    return FileResponse(
        path=file.storage_path,
        filename=file.original_name,
        media_type=mime,
        content_disposition_type="inline",
        headers=headers,
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> None:
    """Delete a file (soft delete)."""
    async with db.session() as session:
        if _session_dialect_name(session) == "sqlite":
            id_txt = await sqlite_parent_id_text(session, "files", file_id)
            r = await session.execute(
                text("SELECT user_id, is_deleted FROM files WHERE CAST(id AS TEXT) = :id"),
                {"id": id_txt},
            )
            row = r.mappings().first()
            if row is None or row["is_deleted"]:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found",
                )
            if not same_user_id(row["user_id"], user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this file",
                )
            now = datetime.utcnow()
            await session.execute(
                text(
                    "UPDATE files SET is_deleted = 1, deleted_at = :d, updated_at = :u "
                    "WHERE CAST(id AS TEXT) = :id"
                ),
                {"d": now, "u": now, "id": id_txt},
            )
            return

        file = await session.get(FileModel, file_id)

        if not file or file.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        if file.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this file",
            )

        file.is_deleted = True
        file.deleted_at = datetime.utcnow()
        file.updated_at = datetime.utcnow()
        session.add(file)


@router.get("/{file_id}/info", response_model=FileRead)
async def get_file_info(
    file_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FileRead:
    """Get file metadata without downloading."""
    async with db.session() as session:
        if _session_dialect_name(session) == "sqlite":
            id_txt = await sqlite_parent_id_text(session, "files", file_id)
            r = await session.execute(
                text("SELECT * FROM files WHERE CAST(id AS TEXT) = :id"),
                {"id": id_txt},
            )
            row = r.mappings().first()
            if row is None or row["is_deleted"]:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found",
                )
            file = file_model_from_sqlite_row(row)
            if not same_user_id(file.user_id, user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this file",
                )
            return FileRead.model_validate(file)

        file = await session.get(FileModel, file_id)

        if not file or file.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        if file.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this file",
            )

        return FileRead.model_validate(file)
