"""File Operations Tool — file and directory operations.

Provides operations for listing, moving, copying, and deleting files,
as well as directory management and file information retrieval.

Renamed from ``FileManagerTool`` to ``FileOpsTool`` to avoid confusion
with :class:`~leagent.file.service.FileService`.
"""

from __future__ import annotations

import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_VIRTUAL_ROOT_ALIASES = frozenset(("/", ".", "./", "~", ""))


def _resolve_session_upload_root(context: ToolContext) -> str | None:
    """Derive the on-disk upload directory for the current session.

    Uses the sandbox's allowed roots (the authoritative source for
    permitted paths) so the resolved directory is always inside the
    sandbox.  Returns ``None`` only when no roots are configured at all.
    """
    from leagent.file.sandbox import _get_allowed_roots

    roots = _get_allowed_roots()
    if not roots:
        return None

    base = roots[0]

    session_id = context.session_id
    if session_id:
        root = base / str(session_id)
        root.mkdir(parents=True, exist_ok=True)
        return str(root)

    return str(base)


class FileOpsTool(SyncTool):
    """Manage files and directories.

    Features:
    - List files and directories with filters
    - Move, copy, and delete files
    - Create and remove directories
    - Get file information (size, type, dates)
    - Recursive operations
    - Glob pattern matching
    """

    name = "file_manager"
    description = (
        "Manage files and directories with operations like list, move, copy, delete, "
        "create directories, and retrieve file information (size, type, modification date). "
        "Operates only inside the allowed sandbox: session upload directory and files the "
        "user attached through the app (or paths explicitly allowed by server config). "
        "IDE references such as @file:name.json do not copy the file here—if the session "
        "upload folder is empty, the user must attach/upload the file in chat or paste its "
        "contents. Use path '/' or '.' to browse the current session's file root."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 120
    aliases = ["files", "fs", "file_ops"]
    search_hint = "file directory list move copy delete mkdir info glob tree"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "block"
    max_result_size_chars = 200_000
    path_params = ()
    output_path_params = ("path", "destination")

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "list")
        path = (params or {}).get("path", "")
        return f"File operation: {op}{f' on {path}' if path else ''}"

    # -- Path normalisation ------------------------------------------------

    def _normalise_virtual_paths(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        """Replace virtual-root aliases with the real session upload dir.

        Mutates *params* in-place so that both the sandbox check and the
        subsequent execution see the resolved physical path.
        """
        raw_path = (params.get("path") or "").strip()
        if raw_path.rstrip("/") in _VIRTUAL_ROOT_ALIASES or raw_path in _VIRTUAL_ROOT_ALIASES:
            resolved = _resolve_session_upload_root(context)
            if resolved:
                params["path"] = resolved
                logger.debug(
                    "file_manager_virtual_root_resolved",
                    original=raw_path,
                    resolved=resolved,
                )

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        """Normalise virtual roots, then delegate to the standard sandbox."""
        self._normalise_virtual_paths(params, context)
        super()._enforce_path_sandbox(params, context)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "list",
                        "info",
                        "move",
                        "copy",
                        "delete",
                        "mkdir",
                        "rmdir",
                        "exists",
                        "glob",
                        "tree",
                    ],
                    "description": "File operation to perform.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Target path under the session sandbox or an attached file. "
                        "Bare filenames and @file:filename resolve only for uploaded "
                        "attachments, not for workspace-only IDE references. "
                        "For mkdir, the path may not exist yet."
                    ),
                },
                "destination": {
                    "type": "string",
                    "description": "Destination path for move/copy operations.",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern for filtering (e.g., '*.txt', '**/*.py').",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Enable recursive operation for directories.",
                    "default": False,
                },
                "include_hidden": {
                    "type": "boolean",
                    "description": "Include hidden files (starting with '.').",
                    "default": False,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum depth for recursive operations.",
                    "minimum": 1,
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Overwrite existing files in move/copy.",
                    "default": False,
                },
                "file_type": {
                    "type": "string",
                    "enum": ["all", "file", "directory", "symlink"],
                    "description": "Filter by file type in list operation.",
                    "default": "all",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["name", "size", "modified", "created", "type"],
                    "description": "Sort criteria for list operation.",
                    "default": "name",
                },
                "sort_order": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort order.",
                    "default": "asc",
                },
            },
            "required": ["operation", "path"],
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute file operation.

        Args:
            params: Tool parameters including operation and path.
            context: Execution context.

        Returns:
            Dictionary containing operation result.

        Raises:
            ValueError: If parameters are invalid.
            FileNotFoundError: If target path doesn't exist.
            PermissionError: If operation is not permitted.
        """
        operation = params["operation"]
        path = Path(params["path"]).expanduser().resolve()

        logger.info("Executing file operation", operation=operation, path=str(path))

        operations = {
            "list": self._list_directory,
            "info": self._get_file_info,
            "move": self._move_file,
            "copy": self._copy_file,
            "delete": self._delete_file,
            "mkdir": self._make_directory,
            "rmdir": self._remove_directory,
            "exists": self._check_exists,
            "glob": self._glob_files,
            "tree": self._get_tree,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        result = operations[operation](path, params)

        logger.info("File operation complete", operation=operation, path=str(path))
        return result

    def _list_directory(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """List directory contents."""
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        include_hidden = params.get("include_hidden", False)
        file_type = params.get("file_type", "all")
        sort_by = params.get("sort_by", "name")
        sort_order = params.get("sort_order", "asc")
        pattern = params.get("pattern")

        entries = []
        items = path.glob(pattern) if pattern else path.iterdir()

        for item in items:
            if not include_hidden and item.name.startswith("."):
                continue

            if file_type == "file" and not item.is_file():
                continue
            if file_type == "directory" and not item.is_dir():
                continue
            if file_type == "symlink" and not item.is_symlink():
                continue

            entry = self._get_entry_info(item)
            entries.append(entry)

        reverse = sort_order == "desc"
        sort_keys = {
            "name": lambda x: x["name"].lower(),
            "size": lambda x: x.get("size", 0),
            "modified": lambda x: x.get("modified", ""),
            "created": lambda x: x.get("created", ""),
            "type": lambda x: x["type"],
        }
        entries.sort(key=sort_keys.get(sort_by, sort_keys["name"]), reverse=reverse)

        return {
            "path": str(path),
            "entries": entries,
            "count": len(entries),
        }

    def _get_file_info(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Get detailed file information."""
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        stat_info = path.stat()
        info = self._get_entry_info(path)

        info.update({
            "absolute_path": str(path.absolute()),
            "permissions": stat.filemode(stat_info.st_mode),
            "mode": oct(stat_info.st_mode),
            "uid": stat_info.st_uid,
            "gid": stat_info.st_gid,
            "inode": stat_info.st_ino,
            "device": stat_info.st_dev,
            "hard_links": stat_info.st_nlink,
        })

        if path.is_symlink():
            info["symlink_target"] = str(path.readlink())

        return info

    def _move_file(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Move file or directory."""
        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {path}")

        destination = params.get("destination")
        if not destination:
            raise ValueError("Destination path is required for move operation")

        dest_path = Path(destination).expanduser().resolve()
        overwrite = params.get("overwrite", False)

        if dest_path.exists() and not overwrite:
            raise FileExistsError(f"Destination already exists: {dest_path}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest_path))

        return {
            "source": str(path),
            "destination": str(dest_path),
            "success": True,
        }

    def _copy_file(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Copy file or directory."""
        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {path}")

        destination = params.get("destination")
        if not destination:
            raise ValueError("Destination path is required for copy operation")

        dest_path = Path(destination).expanduser().resolve()
        overwrite = params.get("overwrite", False)

        if dest_path.exists() and not overwrite:
            raise FileExistsError(f"Destination already exists: {dest_path}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if path.is_dir():
            if dest_path.exists():
                shutil.rmtree(str(dest_path))
            shutil.copytree(str(path), str(dest_path))
        else:
            shutil.copy2(str(path), str(dest_path))

        return {
            "source": str(path),
            "destination": str(dest_path),
            "success": True,
            "is_directory": path.is_dir(),
        }

    def _delete_file(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Delete file or directory."""
        if not path.exists():
            return {
                "path": str(path),
                "success": True,
                "message": "Path does not exist (already deleted)",
            }

        recursive = params.get("recursive", False)

        if path.is_dir():
            if recursive:
                shutil.rmtree(str(path))
            else:
                path.rmdir()
        else:
            path.unlink()

        return {
            "path": str(path),
            "success": True,
        }

    def _make_directory(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Create directory."""
        recursive = params.get("recursive", False)

        if path.exists():
            if path.is_dir():
                return {
                    "path": str(path),
                    "success": True,
                    "created": False,
                    "message": "Directory already exists",
                }
            raise FileExistsError(f"Path exists but is not a directory: {path}")

        if recursive:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir()

        return {
            "path": str(path),
            "success": True,
            "created": True,
        }

    def _remove_directory(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Remove directory."""
        if not path.exists():
            return {
                "path": str(path),
                "success": True,
                "message": "Directory does not exist",
            }

        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        recursive = params.get("recursive", False)

        if recursive:
            shutil.rmtree(str(path))
        else:
            path.rmdir()

        return {
            "path": str(path),
            "success": True,
        }

    def _check_exists(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Check if path exists."""
        exists = path.exists()
        result = {
            "path": str(path),
            "exists": exists,
        }

        if exists:
            result["type"] = "directory" if path.is_dir() else "file"
            result["is_symlink"] = path.is_symlink()

        return result

    def _glob_files(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Find files matching glob pattern."""
        pattern = params.get("pattern", "*")
        recursive = params.get("recursive", False)
        include_hidden = params.get("include_hidden", False)
        max_depth = params.get("max_depth")

        if not path.is_dir():
            raise ValueError(f"Path must be a directory for glob: {path}")

        if recursive and not pattern.startswith("**"):
            pattern = f"**/{pattern}"

        matches = []
        for match in path.glob(pattern):
            if not include_hidden and any(p.startswith(".") for p in match.parts):
                continue

            if max_depth:
                relative = match.relative_to(path)
                if len(relative.parts) > max_depth:
                    continue

            matches.append({
                "path": str(match),
                "name": match.name,
                "type": "directory" if match.is_dir() else "file",
                "size": match.stat().st_size if match.is_file() else 0,
            })

        return {
            "base_path": str(path),
            "pattern": pattern,
            "matches": matches,
            "count": len(matches),
        }

    def _get_tree(self, path: Path, params: dict[str, Any]) -> dict[str, Any]:
        """Get directory tree structure."""
        if not path.is_dir():
            raise ValueError(f"Path must be a directory: {path}")

        max_depth = params.get("max_depth", 3)
        include_hidden = params.get("include_hidden", False)

        def build_tree(current: Path, depth: int) -> dict[str, Any]:
            node: dict[str, Any] = {
                "name": current.name or str(current),
                "type": "directory" if current.is_dir() else "file",
            }

            if current.is_file():
                node["size"] = current.stat().st_size
            elif current.is_dir() and depth < max_depth:
                children = []
                try:
                    for child in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                        if not include_hidden and child.name.startswith("."):
                            continue
                        children.append(build_tree(child, depth + 1))
                except PermissionError:
                    node["error"] = "Permission denied"
                node["children"] = children

            return node

        tree = build_tree(path, 0)
        return {
            "path": str(path),
            "tree": tree,
            "max_depth": max_depth,
        }

    def _get_entry_info(self, item: Path) -> dict[str, Any]:
        """Get basic information for a file or directory."""
        try:
            stat_info = item.stat()
            entry: dict[str, Any] = {
                "name": item.name,
                "path": str(item),
                "type": "directory" if item.is_dir() else "symlink" if item.is_symlink() else "file",
                "size": stat_info.st_size,
                "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                "accessed": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
                "created": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            }

            if item.is_file():
                entry["extension"] = item.suffix.lower() if item.suffix else None

            return entry
        except (OSError, PermissionError) as e:
            return {
                "name": item.name,
                "path": str(item),
                "error": str(e),
            }
