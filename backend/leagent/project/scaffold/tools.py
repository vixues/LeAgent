"""LLM-facing tools that drive the coding-project supervisor."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from leagent.agent.runtime_profile import resolve_runtime_budget
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.project.fs import (
    MAX_TEXT_FILE_BYTES,
    ProjectPathError,
    format_lines_with_numbers,
    read_text_with_detection,
    resolve_in_project,
)

logger = structlog.get_logger(__name__)


def _require_user_id(context: ToolContext) -> UUID:
    raw = context.user_id
    if not raw:
        raise PermissionError(
            "Coding-project tools require an authenticated user_id in the context."
        )
    if isinstance(raw, UUID):
        return raw
    return UUID(str(raw))


def _get_manager() -> Any:
    from leagent.project.manager import (
        get_coding_projects_service,
    )

    return get_coding_projects_service()


def _invalid_uuid_message(field_name: str) -> str:
    return (
        f"{field_name} must be a valid full UUID (36 characters including hyphens). "
        "Copy the id exactly from coding_project_scaffold, coding_project_status, "
        "or the UI without truncating."
    )


def _parse_uuid_param(value: Any, field_name: str) -> tuple[UUID | None, str | None]:
    """Parse a UUID from tool input.

    Returns ``(uuid, None)`` on success, or ``(None, error_message)`` when
    the value is missing or not a valid UUID (including truncated strings).
    """
    try:
        if isinstance(value, UUID):
            return value, None
        text = str(value).strip()
        if not text:
            return None, _invalid_uuid_message(field_name)
        return UUID(text), None
    except (ValueError, TypeError):
        return None, _invalid_uuid_message(field_name)


class CodingProjectScaffoldTool(BaseTool):
    """Copy a template into a new directory and persist a project row."""

    name = "coding_project_scaffold"
    description = (
        "Scaffold a new runnable project from a template. Pick "
        "`vanilla-html` or `vite-react` for a web frontend, `fastapi` "
        "for a Python backend. Returns the new project_id; pair this "
        "with `coding_project_run` to boot the dev server."
    )
    category = ToolCategory.CODE
    aliases = ["scaffold_project", "new_coding_project"]
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "block"
    timeout_sec = 60
    max_result_size_chars = 8000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable project name (200 char limit).",
                    "minLength": 1,
                    "maxLength": 200,
                },
                "template": {
                    "type": "string",
                    "description": (
                        "Template name. Built-ins: `vanilla-html`, "
                        "`vite-react`, `fastapi`. Use `coding_project_status` "
                        "or the REST `/templates` endpoint to discover others."
                    ),
                    "minLength": 1,
                    "maxLength": 64,
                },
                "description": {
                    "type": "string",
                    "description": "Optional short description (500 char limit).",
                    "maxLength": 500,
                },
                "folder_id": {
                    "type": "string",
                    "description": (
                        "Optional ID of an existing Folder to bind the "
                        "project to. When omitted a fresh project-mode "
                        "Folder row is created automatically. If set, pass "
                        "the full UUID string (36 characters); never truncate."
                    ),
                },
                "into_path": {
                    "type": "string",
                    "description": (
                        "Optional absolute path to scaffold into. Must "
                        "resolve to an existing directory under the "
                        "configured allow-list."
                    ),
                    "maxLength": 1024,
                },
            },
            "required": ["name", "template"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        name = (params or {}).get("name")
        return f"Scaffolding coding project {name!r}" if name else "Scaffolding coding project"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        user_id = _require_user_id(context)
        manager = _get_manager()
        folder_id_raw = params.get("folder_id")
        folder_id: UUID | None = None
        if folder_id_raw is not None and str(folder_id_raw).strip():
            parsed, fid_err = _parse_uuid_param(folder_id_raw, "folder_id")
            if fid_err:
                return {"error": fid_err}
            folder_id = parsed

        try:
            project = await manager.scaffold(
                user_id=user_id,
                name=str(params["name"]),
                template=str(params["template"]),
                folder_id=folder_id,
                into_path=params.get("into_path"),
                description=params.get("description"),
            )
        except (ValueError, FileExistsError) as exc:
            return {"error": str(exc)}

        return {
            "project_id": str(project.id),
            "name": project.name,
            "template": project.template,
            "runtime_kind": project.runtime_kind.value
            if hasattr(project.runtime_kind, "value")
            else str(project.runtime_kind),
            "root_path": project.root_path,
            "folder_id": str(project.folder_id) if project.folder_id else None,
            "status": project.status.value
            if hasattr(project.status, "value")
            else str(project.status),
        }


class CodingProjectRunTool(BaseTool):
    """Boot the supervised dev server and return a signed preview URL."""

    name = "coding_project_run"
    description = (
        "Start (or restart) the dev server for an existing coding project. "
        "Frontend templates run via Vite or python http.server; FastAPI "
        "templates run via uvicorn. Returns the signed preview URL the "
        "user can open inline. Always tell the user to click the URL."
    )
    category = ToolCategory.CODE
    aliases = ["run_coding_project", "start_dev_server"]
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "block"
    timeout_sec = int(resolve_runtime_budget("coding_long").task_timeout_sec)
    max_result_size_chars = 8000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Coding project id (canonical UUID string, 36 characters "
                        "including hyphens). Copy exactly from scaffold/status — "
                        "do not truncate."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Starting coding-project dev server"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        user_id = _require_user_id(context)
        manager = _get_manager()
        project_id, pid_err = _parse_uuid_param(params.get("project_id"), "project_id")
        if pid_err or project_id is None:
            return {"error": pid_err or _invalid_uuid_message("project_id")}

        try:
            project, running, token = await manager.start(
                project_id=project_id, user_id=user_id
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

        preview_url = manager.build_preview_url(project.id, token, sub_path="")
        return {
            "project_id": str(project.id),
            "status": project.status.value
            if hasattr(project.status, "value")
            else str(project.status),
            "runtime_kind": project.runtime_kind.value
            if hasattr(project.runtime_kind, "value")
            else str(project.runtime_kind),
            "preview_url": preview_url,
            "preview_token": token,
            "host": running.host,
            "port": running.port,
            "pid": running.pid,
        }


class CodingProjectStopTool(BaseTool):
    """Stop the dev server for a project (graceful, then forced)."""

    name = "coding_project_stop"
    description = (
        "Stop the dev server for a coding project. Idempotent: returns "
        "successfully even when nothing is running."
    )
    category = ToolCategory.CODE
    aliases = ["stop_coding_project"]
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "block"
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Coding project id (36-character UUID). Copy exactly; "
                        "do not truncate."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        user_id = _require_user_id(context)
        manager = _get_manager()
        project_id, pid_err = _parse_uuid_param(params.get("project_id"), "project_id")
        if pid_err or project_id is None:
            return {"error": pid_err or _invalid_uuid_message("project_id")}
        try:
            project = await manager.stop(project_id=project_id, user_id=user_id)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
        return {
            "project_id": str(project.id),
            "status": project.status.value
            if hasattr(project.status, "value")
            else str(project.status),
        }


class CodingProjectStatusTool(BaseTool):
    """Report the live status of a coding project."""

    name = "coding_project_status"
    description = (
        "Return the runtime status for a coding project (idle / starting "
        "/ running / stopping / crashed) plus its last-allocated port."
    )
    category = ToolCategory.CODE
    aliases = ["coding_project_state"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    timeout_sec = 10

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Coding project id (36-character UUID). Copy exactly; "
                        "do not truncate."
                    ),
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        user_id = _require_user_id(context)
        manager = _get_manager()
        project_id, pid_err = _parse_uuid_param(params.get("project_id"), "project_id")
        if pid_err or project_id is None:
            return {"error": pid_err or _invalid_uuid_message("project_id")}
        try:
            project = await manager.get_for_user(project_id, user_id)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
        return {
            "project_id": str(project.id),
            "name": project.name,
            "template": project.template,
            "runtime_kind": project.runtime_kind.value
            if hasattr(project.runtime_kind, "value")
            else str(project.runtime_kind),
            "status": project.status.value
            if hasattr(project.status, "value")
            else str(project.status),
            "port": project.port,
            "pid": project.pid,
            "is_running": manager.supervisor.is_running(project.id),
            "root_path": project.root_path,
        }


class CodingProjectReadTool(BaseTool):
    """Read a text file inside a coding project's on-disk root."""

    name = "coding_project_read"
    description = (
        "Read a text file under a coding project's root (from "
        "`coding_project_scaffold` / `coding_project_status`) and return "
        "line-numbered content like `project_read`. Pass `project_id` and a "
        "path relative to that root (e.g. `app.js`). Use `offset`/`limit` "
        "for large files."
    )
    category = ToolCategory.CODE
    aliases = ["read_coding_project_file"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    timeout_sec = 30
    max_result_size_chars = 200_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Coding project id (36-character UUID). Copy exactly; "
                        "do not truncate."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Path relative to the project root (e.g. `index.html`, "
                        "`src/main.ts`). Use forward slashes."
                    ),
                    "minLength": 1,
                },
                "offset": {
                    "type": "integer",
                    "description": "1-indexed first line to render.",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to render.",
                    "minimum": 1,
                    "maximum": 4000,
                    "default": 2000,
                },
            },
            "required": ["project_id", "path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        p = (params or {}).get("path")
        return f"Reading {p}" if p else "Reading coding project file"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        user_id = _require_user_id(context)
        manager = _get_manager()
        project_id, pid_err = _parse_uuid_param(params.get("project_id"), "project_id")
        if pid_err or project_id is None:
            return {"error": pid_err or _invalid_uuid_message("project_id")}

        try:
            project = await manager.get_for_user(project_id, user_id)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

        try:
            root = Path(str(project.root_path)).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            return {"error": f"Invalid project root_path: {exc}"}

        if not root.exists() or not root.is_dir():
            return {
                "error": (
                    f"Project root does not exist or is not a directory: {root}"
                ),
            }

        raw_path = params.get("path")
        if raw_path is None or not str(raw_path).strip():
            return {"error": "path must be a non-empty string."}

        try:
            resolved = resolve_in_project(root, str(raw_path), must_exist=True)
        except ProjectPathError as exc:
            return {"error": str(exc)}
        except FileNotFoundError as exc:
            return {"error": str(exc)}

        if not resolved.abs_path.is_file():
            return {
                "error": f"Not a file: {resolved.rel_path}",
                "path": resolved.rel_path,
            }

        try:
            size = resolved.abs_path.stat().st_size
        except OSError as exc:
            return {"error": str(exc), "path": resolved.rel_path}

        if size > MAX_TEXT_FILE_BYTES:
            return {
                "error": (
                    f"File is too large to read in one shot ({size} bytes; "
                    f"limit {MAX_TEXT_FILE_BYTES}). Use offset/limit or "
                    "project_grep for targeted lookups."
                ),
                "path": resolved.rel_path,
                "size": size,
            }

        try:
            text, encoding = read_text_with_detection(resolved.abs_path)
        except UnicodeDecodeError as exc:
            return {
                "error": f"File is not text or has unknown encoding: {exc}",
                "path": resolved.rel_path,
                "size": size,
            }
        except OSError as exc:
            return {"error": str(exc), "path": resolved.rel_path}

        offset = int(params.get("offset") or 1)
        limit = int(params.get("limit") or 2000)
        rendered, start, end = format_lines_with_numbers(
            text, offset=offset, limit=limit
        )
        total_lines = text.count("\n") + (
            0 if text.endswith("\n") or not text else 1
        )
        return {
            "path": resolved.rel_path,
            "encoding": encoding,
            "size": size,
            "total_lines": total_lines,
            "start_line": start,
            "end_line": end,
            "content": rendered,
            "truncated": end < total_lines,
        }


class CodingProjectLogsTool(BaseTool):
    """Return the last N log lines from the supervised dev server."""

    name = "coding_project_logs"
    description = (
        "Return recent stdout / stderr lines captured by the supervisor. "
        "Use after `coding_project_run` to verify the server started, "
        "or after a code change to inspect the reload output."
    )
    category = ToolCategory.CODE
    aliases = ["coding_project_log"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    timeout_sec = 10
    max_result_size_chars = 40_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Coding project id (36-character UUID). Copy exactly; "
                        "do not truncate."
                    ),
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of trailing log lines to return.",
                    "minimum": 1,
                    "maximum": 2000,
                    "default": 200,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        user_id = _require_user_id(context)
        manager = _get_manager()
        project_id, pid_err = _parse_uuid_param(params.get("project_id"), "project_id")
        if pid_err or project_id is None:
            return {"error": pid_err or _invalid_uuid_message("project_id")}
        try:
            await manager.get_for_user(project_id, user_id)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
        lines = manager.snapshot_logs(
            project_id, max_lines=int(params.get("max_lines") or 200)
        )
        return {
            "project_id": str(project_id),
            "is_running": manager.supervisor.is_running(project_id),
            "log_lines": [line.to_dict() for line in lines],
        }
