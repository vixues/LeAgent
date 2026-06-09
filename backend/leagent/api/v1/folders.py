"""Folder management API endpoints.

In addition to the original DB-backed folder CRUD, this router also
implements the **code-project mode**: when ``Folder.is_project`` is
true the folder is bound to an absolute on-disk directory
(``Folder.project_path``) the coding agent and ``project_*`` tools
operate on. The ``/folders/{id}/project/...`` endpoints expose a
read-only filesystem and git view of that directory so the frontend
``FolderPage`` can render a real project tree, file viewer, and
commit history without the LLM loop in the middle.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from leagent.schema.api import PaginatedResponse
from leagent.services.auth import CurrentUserId
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.sqlite_compat import load_entity_by_id
from leagent.services.database.models import (
    Folder,
    FolderCreate,
    FolderRead,
    FolderUpdate,
)
from leagent.project.git import (
    GitCommandError,
    GitNotInstalledError,
    git_diff_for_commit,
    git_diff_worktree,
    git_init,
    git_log,
    git_show_file,
    git_status_porcelain,
    is_git_repo,
)
from leagent.project.paths import (
    ProjectPathSafetyError,
    resolve_owned_project_folder,
    validate_project_path,
)
from leagent.project.fs import (
    MAX_TEXT_FILE_BYTES,
    IgnoreMatcher,
    format_lines_with_numbers,
    read_text_with_detection,
    resolve_in_project,
)

router = APIRouter()


class FolderCreateRequest(BaseModel):
    """Request schema for creating a folder."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default="📁", max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)
    parent_id: Optional[UUID] = None


class FolderUpdateRequest(BaseModel):
    """Request schema for updating a folder."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)
    parent_id: Optional[UUID] = None
    position: Optional[int] = Field(default=None, ge=0)


class FolderTreeNode(BaseModel):
    """Folder tree node with children."""

    id: UUID
    name: str
    description: Optional[str]
    icon: Optional[str]
    color: Optional[str]
    parent_id: Optional[UUID]
    position: int
    file_count: int
    flow_count: int
    #: Code-project mode — same semantics as :class:`FolderRead`.
    is_project: bool = False
    project_path: Optional[str] = None
    children: list["FolderTreeNode"] = Field(default_factory=list)


@router.post("", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: FolderCreateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FolderRead:
    """Create a new folder."""
    async with db.session() as session:
        if data.parent_id:
            parent = await load_entity_by_id(session, Folder, data.parent_id, parent_table="folders")
            if not parent or parent.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found",
                )
            if parent.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to parent folder",
                )

        max_pos_query = select(func.max(Folder.position)).where(
            Folder.user_id == user_id,
            Folder.parent_id == data.parent_id,
            Folder.is_deleted == False,
        )
        result = await session.exec(max_pos_query)
        max_pos = result.one() or -1

        folder = Folder(
            name=data.name,
            description=data.description,
            icon=data.icon,
            color=data.color,
            parent_id=data.parent_id,
            user_id=user_id,
            position=max_pos + 1,
        )
        session.add(folder)
        await session.flush()
        await session.refresh(folder)

        return FolderRead.model_validate(folder)


@router.get("", response_model=PaginatedResponse[FolderRead])
async def list_folders(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    parent_id: Optional[UUID] = Query(default=None),
) -> PaginatedResponse[FolderRead]:
    """List folders for the current user."""
    async with db.session() as session:
        query = select(Folder).where(
            Folder.user_id == user_id,
            Folder.is_deleted == False,
        )

        if parent_id is not None:
            query = query.where(Folder.parent_id == parent_id)
        else:
            query = query.where(Folder.parent_id == None)

        count_query = select(func.count()).select_from(query.subquery())
        count_result = await session.exec(count_query)
        total = count_result.one()

        query = query.order_by(col(Folder.position).asc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.exec(query)
        folders = list(result.all())

        return PaginatedResponse[FolderRead](
            items=[FolderRead.model_validate(f) for f in folders],
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
            has_prev=page > 1,
        )


@router.get("/tree", response_model=list[FolderTreeNode])
async def get_folder_tree(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[FolderTreeNode]:
    """Get the complete folder tree for the current user."""
    async with db.session() as session:
        query = select(Folder).where(
            Folder.user_id == user_id,
            Folder.is_deleted == False,
        ).order_by(col(Folder.position).asc())

        result = await session.exec(query)
        all_folders = list(result.all())

        folder_map: dict[UUID, FolderTreeNode] = {}
        for f in all_folders:
            folder_map[f.id] = FolderTreeNode(
                id=f.id,
                name=f.name,
                description=f.description,
                icon=f.icon,
                color=f.color,
                parent_id=f.parent_id,
                position=f.position,
                file_count=f.file_count,
                flow_count=f.flow_count,
                is_project=bool(getattr(f, "is_project", False)),
                project_path=getattr(f, "project_path", None),
                children=[],
            )

        root_folders: list[FolderTreeNode] = []
        for f in all_folders:
            node = folder_map[f.id]
            if f.parent_id and f.parent_id in folder_map:
                folder_map[f.parent_id].children.append(node)
            else:
                root_folders.append(node)

        return root_folders


@router.get("/{folder_id}", response_model=FolderRead)
async def get_folder(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FolderRead:
    """Get folder details by ID."""
    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, folder_id, parent_table="folders")

        if not folder or folder.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        if folder.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this folder",
            )

        return FolderRead.model_validate(folder)


@router.put("/{folder_id}", response_model=FolderRead)
async def update_folder(
    folder_id: UUID,
    data: FolderUpdateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FolderRead:
    """Update a folder."""
    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, folder_id, parent_table="folders")

        if not folder or folder.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        if folder.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this folder",
            )

        if data.parent_id is not None and data.parent_id != folder.parent_id:
            if data.parent_id == folder_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Folder cannot be its own parent",
                )

            parent = await load_entity_by_id(session, Folder, data.parent_id, parent_table="folders")
            if not parent or parent.is_deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Parent folder not found",
                )
            if parent.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to parent folder",
                )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(folder, field, value)

        folder.updated_at = datetime.utcnow()
        session.add(folder)
        await session.flush()
        await session.refresh(folder)

        return FolderRead.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    recursive: bool = Query(default=False),
) -> None:
    """Delete a folder. Use recursive=true to delete subfolders."""
    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, folder_id, parent_table="folders")

        if not folder or folder.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )

        if folder.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this folder",
            )

        children_query = select(Folder).where(
            Folder.parent_id == folder_id,
            Folder.is_deleted == False,
        )
        children_result = await session.exec(children_query)
        children = list(children_result.all())

        if children and not recursive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Folder has subfolders. Use recursive=true to delete them.",
            )

        async def soft_delete_recursive(f: Folder) -> None:
            f.is_deleted = True
            f.deleted_at = datetime.utcnow()
            f.updated_at = datetime.utcnow()
            session.add(f)

            sub_query = select(Folder).where(
                Folder.parent_id == f.id,
                Folder.is_deleted == False,
            )
            sub_result = await session.exec(sub_query)
            for sub in sub_result.all():
                await soft_delete_recursive(sub)

        await soft_delete_recursive(folder)


# ---------------------------------------------------------------------------
# Code-project mode
# ---------------------------------------------------------------------------


class FolderProjectUpdateRequest(BaseModel):
    """Request body for ``PATCH /folders/{id}/project``."""

    enabled: bool = Field(
        ...,
        description=(
            "When True, set the folder into code-project mode. When "
            "False, clear ``project_path`` and exit project mode."
        ),
    )
    project_path: Optional[str] = Field(
        default=None,
        max_length=1024,
        description=(
            "Absolute path to the on-disk project root. Required when "
            "``enabled`` is True; ignored otherwise."
        ),
    )


class ProjectTreeEntry(BaseModel):
    """One row in a depth-N project tree listing."""

    name: str
    rel_path: str
    type: str  # "file" | "dir"
    size: Optional[int] = None
    mtime: Optional[float] = None
    is_ignored: bool = False
    has_children: Optional[bool] = None


class ProjectFileResponse(BaseModel):
    """Body of a project file read."""

    rel_path: str
    encoding: Optional[str] = None
    size: int
    line_count: int
    is_binary: bool = False
    truncated: bool = False
    content: str = ""
    start_line: int = 1
    end_line: int = 0


class ProjectGitCommit(BaseModel):
    commit: str
    short: str
    author_name: str
    author_email: str
    date_iso: str
    summary: str


class ProjectGitStatusEntry(BaseModel):
    path: str
    status_code: str


def _safety_to_http(exc: ProjectPathSafetyError) -> HTTPException:
    """Translate a safety failure into an HTTP error.

    Folder-not-in-project / not-owned cases stay generic 4xx so the
    UI can show a single "Project mode is not enabled or accessible"
    message without leaking which specific check failed.
    """
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def _load_project_folder(
    session,
    folder_id: UUID,
    user_id: UUID,
) -> tuple[Folder, Path]:
    """Fetch a folder and resolve its validated ``project_path``.

    Raises HTTP 404 when the folder does not exist or the caller
    does not own it (mirroring how the rest of this router treats
    cross-tenant access). Raises HTTP 409 when project mode is off
    or the configured directory is no longer reachable on disk.
    """
    folder = await load_entity_by_id(session, Folder, folder_id, parent_table="folders")
    if not folder or folder.is_deleted or folder.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found",
        )
    try:
        path = resolve_owned_project_folder(folder, user_id)
    except ProjectPathSafetyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return folder, path


def _resolve_subpath(root: Path, raw: Optional[str]) -> Path:
    """Resolve a relative ``raw`` to an absolute path under ``root``.

    Empty / missing input means "the root itself". Symlink escapes
    and ``..`` traversal are rejected by leveraging the
    :func:`resolve_in_project` helper from the agent-facing tools so
    HTTP and tool layers share the same boundary.
    """
    if raw is None or not raw.strip() or raw.strip() in (".", "/", "./"):
        return root
    rf = resolve_in_project(root, raw, must_exist=False)
    return rf.abs_path


@router.patch("/{folder_id}/project", response_model=FolderRead)
async def update_folder_project(
    folder_id: UUID,
    data: FolderProjectUpdateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FolderRead:
    """Toggle / configure a folder's code-project binding.

    Enabling requires a valid absolute ``project_path`` that exists,
    is a directory, and (when ``FILES_PROJECTS_ALLOWED_ROOTS`` is
    set) lies under one of the allowed prefixes. Disabling clears
    the path so the folder reverts to a plain DB folder.
    """
    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, folder_id, parent_table="folders")
        if not folder or folder.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Folder not found",
            )
        if folder.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this folder",
            )

        if data.enabled:
            if not data.project_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="project_path is required when enabling project mode.",
                )
            try:
                resolved = validate_project_path(data.project_path)
            except ProjectPathSafetyError as exc:
                raise _safety_to_http(exc) from exc
            folder.is_project = True
            folder.project_path = str(resolved)
            folder.project_path_checked_at = datetime.utcnow()
        else:
            folder.is_project = False
            folder.project_path = None
            folder.project_path_checked_at = datetime.utcnow()

        folder.updated_at = datetime.utcnow()
        session.add(folder)
        await session.flush()
        await session.refresh(folder)
        return FolderRead.model_validate(folder)


@router.get("/{folder_id}/project/tree", response_model=list[ProjectTreeEntry])
async def get_project_tree(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    path: str = Query(default="", description="Subpath relative to the project root"),
    depth: int = Query(default=1, ge=1, le=4),
    include_ignored: bool = Query(default=False),
    max_entries: int = Query(default=2000, ge=1, le=20000),
) -> list[ProjectTreeEntry]:
    """List directory entries under ``path`` (depth-N), gitignore-aware.

    Each row carries ``rel_path`` relative to the project root so the
    frontend can request file contents or expand subdirectories
    without having to know about absolute paths. ``is_ignored`` is
    surfaced even when ``include_ignored`` is False because callers
    can choose to render ignored entries with a visual hint and let
    the user opt in.
    """
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)

    base = _resolve_subpath(root, path)
    if not base.exists() or not base.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path {path!r} is not a directory in this project.",
        )

    matcher = IgnoreMatcher(root)

    entries: list[ProjectTreeEntry] = []
    seen = 0

    def _walk(directory: Path, current_depth: int) -> None:
        nonlocal seen
        if seen >= max_entries:
            return
        try:
            children = sorted(
                directory.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except (OSError, PermissionError):
            return
        for child in children:
            if seen >= max_entries:
                return
            try:
                is_dir = child.is_dir() and not child.is_symlink()
            except OSError:
                is_dir = False
            ignored = matcher.is_ignored(child, is_dir=is_dir)
            if ignored and not include_ignored:
                continue
            try:
                rel = child.relative_to(root).as_posix()
            except ValueError:
                continue
            try:
                stat = child.stat()
                size = stat.st_size if not is_dir else None
                mtime = stat.st_mtime
            except OSError:
                size = None
                mtime = None
            has_children: Optional[bool] = None
            if is_dir:
                try:
                    has_children = any(True for _ in child.iterdir())
                except (OSError, PermissionError):
                    has_children = None
            entries.append(
                ProjectTreeEntry(
                    name=child.name,
                    rel_path=rel,
                    type="dir" if is_dir else "file",
                    size=size,
                    mtime=mtime,
                    is_ignored=ignored,
                    has_children=has_children,
                )
            )
            seen += 1
            if is_dir and current_depth + 1 < depth:
                _walk(child, current_depth + 1)

    _walk(base, 0)
    return entries


@router.get("/{folder_id}/project/file", response_model=ProjectFileResponse)
async def get_project_file(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    path: str = Query(..., min_length=1),
    offset: int = Query(default=1, ge=1),
    limit: Optional[int] = Query(default=None, ge=1, le=20000),
) -> ProjectFileResponse:
    """Read a single text file inside the project.

    Binary files (detected via NUL probe) return ``is_binary=True``
    with empty content so the UI can show a "binary file" hint
    instead of corrupted bytes. ``offset`` is 1-indexed. Files
    larger than :data:`MAX_TEXT_FILE_BYTES` return
    ``truncated=True``.
    """
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)

    target = _resolve_subpath(root, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {path!r}",
        )

    try:
        size = target.stat().st_size
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cannot stat file: {exc}",
        ) from exc

    rel = target.relative_to(root).as_posix()
    if size > MAX_TEXT_FILE_BYTES:
        return ProjectFileResponse(
            rel_path=rel,
            size=size,
            line_count=0,
            is_binary=False,
            truncated=True,
            content="",
        )

    try:
        text, encoding = read_text_with_detection(target)
    except UnicodeDecodeError:
        return ProjectFileResponse(
            rel_path=rel,
            size=size,
            line_count=0,
            is_binary=True,
            content="",
        )
    line_count = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    rendered, start_line, end_line = format_lines_with_numbers(
        text,
        offset=offset,
        limit=limit,
    )
    # Strip the LINE_NUM| prefix the agent harness uses; the UI does
    # its own gutter rendering and prefers the raw slice.
    raw_slice_lines = text.splitlines()
    slice_start = max(start_line - 1, 0)
    slice_end = end_line if end_line >= start_line else slice_start
    raw_content = "\n".join(raw_slice_lines[slice_start:slice_end])
    if end_line >= line_count and text.endswith("\n"):
        raw_content += "\n"
    _ = rendered  # rendered is only useful for LLM consumers

    return ProjectFileResponse(
        rel_path=rel,
        encoding=encoding,
        size=size,
        line_count=line_count,
        is_binary=False,
        truncated=False,
        content=raw_content,
        start_line=start_line,
        end_line=end_line,
    )


@router.get(
    "/{folder_id}/project/git/log",
    response_model=list[ProjectGitCommit],
)
async def get_project_git_log(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    path: Optional[str] = Query(default=None, description="Limit history to a single path"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),
) -> list[ProjectGitCommit]:
    """Return commit history, optionally filtered to a single ``path``."""
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)
    if not await is_git_repo(root):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project root is not a git repository.",
        )
    try:
        commits = await git_log(root, path=path, limit=limit, offset=offset)
    except GitNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitCommandError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [ProjectGitCommit(**c.to_dict()) for c in commits]


@router.get("/{folder_id}/project/git/show")
async def get_project_git_show(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    commit: str = Query(..., min_length=1, max_length=200),
    path: str = Query(..., min_length=1),
) -> dict:
    """Return file contents at ``commit``."""
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)
    if not await is_git_repo(root):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project root is not a git repository.",
        )
    try:
        body = await git_show_file(root, commit, path)
    except GitNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (GitCommandError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"commit": commit, "path": path, "content": body}


@router.get("/{folder_id}/project/git/diff")
async def get_project_git_diff(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    commit: Optional[str] = Query(default=None, max_length=200),
    path: Optional[str] = Query(default=None),
    against_worktree: bool = Query(default=False),
) -> dict:
    """Return a unified diff for ``commit`` or the unstaged worktree.

    Pass ``against_worktree=true`` to inspect uncommitted changes
    relative to ``HEAD`` (no ``commit`` needed). Otherwise, supply a
    commit SHA to see what that commit changed.
    """
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)
    if not await is_git_repo(root):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project root is not a git repository.",
        )
    try:
        if against_worktree:
            diff = await git_diff_worktree(root, path=path)
            return {"commit": None, "path": path, "diff": diff, "scope": "worktree"}
        if not commit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either commit or against_worktree=true is required.",
            )
        diff = await git_diff_for_commit(root, commit, path=path)
    except GitNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (GitCommandError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"commit": commit, "path": path, "diff": diff, "scope": "commit"}


@router.get(
    "/{folder_id}/project/git/status",
    response_model=list[ProjectGitStatusEntry],
)
async def get_project_git_status(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[ProjectGitStatusEntry]:
    """Return ``git status --porcelain`` entries (empty when not a repo)."""
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)
    try:
        entries = await git_status_porcelain(root)
    except GitNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return [ProjectGitStatusEntry(**e.to_dict()) for e in entries]


@router.post("/{folder_id}/project/git/init")
async def post_project_git_init(
    folder_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> dict:
    """Initialise a git repository inside the project root (idempotent)."""
    async with db.session() as session:
        _, root = await _load_project_folder(session, folder_id, user_id)
    try:
        result = await git_init(root)
    except GitNotInstalledError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GitCommandError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"folder_id": str(folder_id), "path": str(root), **result}
