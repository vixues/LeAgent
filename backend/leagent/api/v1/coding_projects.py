"""Coding-projects HTTP + WebSocket API.

This is the user-facing surface for the live-runtime feature: the
frontend (and curl-based scripts) call these endpoints to scaffold
a project from a template, run / stop the supervised dev server,
tail logs, and reach the running server through a signed reverse
proxy.

Mounted at ``/api/v1/coding-projects``. Token-gated preview routes
verify the JWT minted by :func:`mint_preview_token` against the URL's
``project_id`` so a leaked URL only ever reveals the project it was
issued for.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from leagent.services.auth.tokens import TokenError
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from leagent.config.settings import Settings, get_settings
from leagent.services.auth import CurrentUserId
from leagent.project.binaries import CodingBinaryNotAllowedError
from leagent.project.manager import (
    CodingProjectManager,
    CodingProjectNotFoundError,
    CodingProjectQuotaError,
)
from leagent.project.paths import ProjectPathSafetyError
from leagent.project.preview_tokens import decode_preview_token, mint_preview_token
from leagent.project.proxy import forward_http, forward_websocket
from leagent.project.runtime import StartTimeoutError
from leagent.project.templates import list_templates
from leagent.project.git import (
    GitCommandError,
    GitNotInstalledError,
    git_diff_for_commit,
    git_diff_worktree,
    git_log,
    git_show_file,
    git_status_porcelain,
    is_git_repo,
)
from leagent.project.workspace import (
    UnsafePathError,
    build_tree,
    git_snapshot,
    read_text_file,
)
from leagent.db.models import (
    CodingProjectRead,
    CodingProjectRuntimeKind,
    CodingProjectStatus,
)

router = APIRouter()


def get_coding_projects(
    settings: Annotated[Settings, Depends(get_settings)],
) -> CodingProjectManager:
    """Resolve the manager from the running ServiceManager.

    Raises HTTP 503 when the service is disabled or has not started
    so callers see a clear error instead of an obscure ``RuntimeError``.
    """
    try:
        from leagent.project.manager import (
            get_coding_projects_service,
        )

        return get_coding_projects_service()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Coding-projects service is not available.",
        ) from exc


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TemplateInfo(BaseModel):
    name: str
    runtime_kind: str
    title: str
    description: str
    needs_install: bool


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    folder_id: Optional[UUID] = None
    into_path: Optional[str] = Field(default=None, max_length=1024)


class RunResponse(BaseModel):
    project_id: UUID
    status: CodingProjectStatus
    runtime_kind: CodingProjectRuntimeKind
    port: int
    host: str
    preview_url: str
    preview_token: str
    expires_at: float
    health_path: str


class StatusResponse(BaseModel):
    project_id: UUID
    status: CodingProjectStatus
    runtime_kind: CodingProjectRuntimeKind
    port: Optional[int]
    pid: Optional[int]
    last_started_at: Optional[datetime]
    last_stopped_at: Optional[datetime]
    is_running: bool


# ---------------------------------------------------------------------------
# Templates + CRUD
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateInfo])
async def get_templates() -> list[TemplateInfo]:
    return [
        TemplateInfo(
            name=t.name,
            runtime_kind=t.runtime_kind,
            title=t.title,
            description=t.description,
            needs_install=t.needs_install,
        )
        for t in list_templates()
    ]


@router.post("", response_model=CodingProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> CodingProjectRead:
    try:
        project = await manager.scaffold(
            user_id=user_id,
            name=body.name,
            template=body.template,
            folder_id=body.folder_id,
            into_path=body.into_path,
            description=body.description,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ProjectPathSafetyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return CodingProjectRead.model_validate(project)


@router.get("", response_model=list[CodingProjectRead])
async def list_projects(
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> list[CodingProjectRead]:
    rows = await manager.list_for_user(user_id)
    return [CodingProjectRead.model_validate(r) for r in rows]


@router.get("/{project_id}", response_model=CodingProjectRead)
async def get_project(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> CodingProjectRead:
    try:
        project = await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc
    return CodingProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> None:
    try:
        await manager.delete(project_id=project_id, user_id=user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc


# ---------------------------------------------------------------------------
# Workspace (read-only tree / file / git)
# ---------------------------------------------------------------------------


@router.get("/{project_id}/workspace/tree")
async def workspace_tree(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    max_depth: int = Query(default=8, ge=1, le=32),
    max_entries: int = Query(default=500, ge=1, le=5000),
    max_children_per_dir: int = Query(default=200, ge=10, le=1000),
) -> dict[str, Any]:
    try:
        project = await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc

    root = Path(project.root_path)
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project root is missing from disk.",
        )

    return await asyncio.to_thread(
        build_tree,
        root,
        max_depth=max_depth,
        max_entries=max_entries,
        max_children_per_dir=max_children_per_dir,
    )


@router.get("/{project_id}/workspace/file")
async def workspace_file(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    path: str = Query(..., min_length=1, max_length=4096),
) -> dict[str, Any]:
    try:
        project = await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc

    root = Path(project.root_path)
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project root is missing from disk.",
        )

    try:
        return await asyncio.to_thread(read_text_file, root, path)
    except UnsafePathError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/{project_id}/workspace/git")
async def workspace_git(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> dict[str, Any]:
    try:
        project = await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc

    root = Path(project.root_path)
    return await git_snapshot(root)


async def _coding_project_root(
    manager: CodingProjectManager,
    project_id: UUID,
    user_id: str,
) -> Path:
    try:
        project = await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc
    return Path(project.root_path)


@router.get("/{project_id}/git/log")
async def coding_project_git_log(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    path: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=100000),
) -> list[dict[str, str]]:
    """Mirror of folders ``/project/git/log`` for coding-projects."""
    root = await _coding_project_root(manager, project_id, user_id)
    if not await is_git_repo(root):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project root is not a git repository.",
        )
    try:
        commits = await git_log(root, path=path, limit=limit, offset=offset)
    except GitNotInstalledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc
    except GitCommandError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    return [c.to_dict() for c in commits]


@router.get("/{project_id}/git/show")
async def coding_project_git_show(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    commit: str = Query(..., min_length=1, max_length=200),
    path: str = Query(..., min_length=1),
) -> dict[str, Any]:
    root = await _coding_project_root(manager, project_id, user_id)
    if not await is_git_repo(root):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project root is not a git repository.",
        )
    try:
        body = await git_show_file(root, commit, path)
    except GitNotInstalledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc
    except (GitCommandError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    return {"commit": commit, "path": path, "content": body}


@router.get("/{project_id}/git/diff")
async def coding_project_git_diff(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    commit: Optional[str] = Query(default=None, max_length=200),
    path: Optional[str] = Query(default=None),
    against_worktree: bool = Query(default=False),
) -> dict[str, Any]:
    root = await _coding_project_root(manager, project_id, user_id)
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc
    except (GitCommandError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    return {"commit": commit, "path": path, "diff": diff, "scope": "commit"}


@router.get("/{project_id}/git/status")
async def coding_project_git_status(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> list[dict[str, str]]:
    root = await _coding_project_root(manager, project_id, user_id)
    try:
        entries = await git_status_porcelain(root)
    except GitNotInstalledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc),
        ) from exc
    return [e.to_dict() for e in entries]


# ---------------------------------------------------------------------------
# Run / stop / status
# ---------------------------------------------------------------------------


@router.post("/{project_id}/run", response_model=RunResponse)
async def run_project(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RunResponse:
    try:
        project, running, token = await manager.start(
            project_id=project_id, user_id=user_id
        )
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc
    except CodingProjectQuotaError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except CodingBinaryNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except StartTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    template = manager.get_template(project.template)
    expires_at = (
        datetime.now(timezone.utc).timestamp()
        + settings.coding_projects.preview_token_ttl_seconds
    )
    preview_url = manager.build_preview_url(project.id, token, sub_path="")
    return RunResponse(
        project_id=project.id,
        status=project.status,
        runtime_kind=project.runtime_kind,
        port=running.port,
        host=running.host,
        preview_url=preview_url,
        preview_token=token,
        expires_at=expires_at,
        health_path=template.health_path,
    )


@router.post("/{project_id}/stop", response_model=StatusResponse)
async def stop_project(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> StatusResponse:
    try:
        project = await manager.stop(project_id=project_id, user_id=user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc
    return StatusResponse(
        project_id=project.id,
        status=project.status,
        runtime_kind=project.runtime_kind,
        port=project.port,
        pid=project.pid,
        last_started_at=project.last_started_at,
        last_stopped_at=project.last_stopped_at,
        is_running=manager.supervisor.is_running(project.id),
    )


@router.get("/{project_id}/status", response_model=StatusResponse)
async def project_status(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
) -> StatusResponse:
    try:
        project = await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc
    return StatusResponse(
        project_id=project.id,
        status=project.status,
        runtime_kind=project.runtime_kind,
        port=project.port,
        pid=project.pid,
        last_started_at=project.last_started_at,
        last_stopped_at=project.last_stopped_at,
        is_running=manager.supervisor.is_running(project.id),
    )


# ---------------------------------------------------------------------------
# Logs (SSE)
# ---------------------------------------------------------------------------


@router.get("/{project_id}/logs")
async def stream_project_logs(
    project_id: UUID,
    user_id: CurrentUserId,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    request: Request,
) -> EventSourceResponse:
    try:
        await manager.get_for_user(project_id, user_id)
    except CodingProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coding project not found"
        ) from exc

    async def _gen() -> Any:
        if not manager.supervisor.is_running(project_id):
            for line in manager.snapshot_logs(project_id):
                yield {"event": "log", "data": json.dumps(line.to_dict())}
            yield {"event": "done", "data": "{}"}
            return
        try:
            async for line in manager.stream_logs(project_id):
                if await request.is_disconnected():
                    break
                if line is None:
                    yield {"event": "done", "data": "{}"}
                    return
                yield {"event": "log", "data": json.dumps(line.to_dict())}
        except asyncio.CancelledError:
            pass
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(_gen())


# ---------------------------------------------------------------------------
# Preview reverse proxy (HTTP + WS)
# ---------------------------------------------------------------------------


def _preview_cookie_name(project_id: UUID) -> str:
    return f"leagent_preview_{project_id.hex}"


def _decode_token_or_401(
    settings: Settings,
    project_id: UUID,
    token: str,
) -> dict[str, Any]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing preview token",
        )
    try:
        claims = decode_preview_token(settings, token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid preview token: {exc}",
        ) from exc
    if claims.get("cpid") != str(project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Preview token does not match this project",
        )
    return claims


@router.api_route(
    "/{project_id}/preview/{sub_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def preview_proxy(
    project_id: UUID,
    sub_path: str,
    request: Request,
    manager: Annotated[CodingProjectManager, Depends(get_coding_projects)],
    settings: Annotated[Settings, Depends(get_settings)],
    token: str = Query(default=""),
) -> Any:
    # Sub-resource requests (JS modules, CSS, images, HMR pings) issued
    # by the previewed page carry no ?token= query, so the first
    # tokened request drops a path-scoped cookie the follow-ups ride on.
    cookie_token = request.cookies.get(_preview_cookie_name(project_id), "")
    effective_token = token or cookie_token
    claims = _decode_token_or_401(settings, project_id, effective_token)

    server = manager.supervisor.get(project_id)
    if server is None or not manager.supervisor.is_running(project_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dev server is not running",
        )

    target_base = manager.supervised_target_base(server)
    upstream_path = manager.supervised_sub_path(server, sub_path)
    response = await forward_http(
        request, target_base=target_base, sub_path=upstream_path
    )
    if token and token != cookie_token:
        max_age = max(60, int(claims.get("exp", 0)) - int(datetime.now(timezone.utc).timestamp()))
        response.set_cookie(
            _preview_cookie_name(project_id),
            token,
            max_age=max_age,
            path=f"/api/v1/coding-projects/{project_id}/",
            httponly=True,
            samesite="lax",
        )
    return response


@router.websocket("/{project_id}/preview-ws/{sub_path:path}")
@router.websocket("/{project_id}/preview/{sub_path:path}")
async def preview_proxy_ws(
    websocket: WebSocket,
    project_id: UUID,
    sub_path: str,
) -> None:
    """Bridge preview WebSockets (Vite HMR connects at the preview base path)."""
    settings = get_settings()
    token = websocket.query_params.get("token", "") or websocket.cookies.get(
        _preview_cookie_name(project_id), ""
    )
    try:
        _decode_token_or_401(settings, project_id, token)
    except HTTPException as exc:
        await websocket.close(code=4401, reason=exc.detail)
        return

    try:
        manager = get_coding_projects(settings)
    except HTTPException:
        await websocket.close(code=4503, reason="service unavailable")
        return

    server = manager.supervisor.get(project_id)
    if server is None or not manager.supervisor.is_running(project_id):
        await websocket.close(code=4409, reason="dev server not running")
        return

    target = manager.supervised_ws_target(server, sub_path)
    try:
        await forward_websocket(
            websocket,
            target_url=target,
            subprotocols=websocket.scope.get("subprotocols", ()) or (),
        )
    except WebSocketDisconnect:
        pass
