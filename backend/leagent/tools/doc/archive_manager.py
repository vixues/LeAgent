"""Archive Manager Tool — list, extract, create, and inspect zip/tar archives."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from typing import Any

from leagent.tools.base import SyncTool, ToolCategory, ToolContext


class ArchiveManagerTool(SyncTool):
    """Manage archive files (zip, tar, tar.gz, tar.bz2, tar.xz).

    Supports listing contents, extracting files, creating archives,
    and retrieving archive metadata without full extraction.
    """

    name = "archive_manager"
    description = (
        "Manage archive files: list contents, extract files, create archives "
        "(zip/tar/tar.gz/tar.bz2/tar.xz), and inspect metadata. "
        "End users can also multi-select files in the chat workspace Files tab "
        "and use compressed ZIP download for owned attachments without calling this tool."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 300
    aliases = ["archive", "zip", "unzip", "tar"]
    search_hint = "archive zip tar extract compress list contents metadata"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    path_params = ()
    output_path_params = ("archive_path", "output_dir")

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: "ToolContext",
    ) -> None:
        super()._enforce_path_sandbox(params, context)

        from leagent.file.sandbox import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")
        for fp in params.get("files") or []:
            if fp and isinstance(fp, str):
                PathSandbox.resolve_safe(
                    fp,
                    context=context,
                    allow_create=False,
                    tool_name=self.name,
                    request_id=str(request_id),
                )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "extract", "create", "info"],
                    "description": "Archive operation to perform.",
                },
                "archive_path": {
                    "type": "string",
                    "description": "Path to the archive file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory to extract files into.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific files to extract, or paths to include when creating.",
                },
                "format": {
                    "type": "string",
                    "enum": ["zip", "tar", "tar.gz", "tar.bz2", "tar.xz"],
                    "description": "Archive format for create operation.",
                },
                "compression_level": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 9,
                    "description": "Compression level (0-9) for zip. Default 6.",
                },
            },
            "required": ["operation", "archive_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "list")
        return f"Managing archive ({op})"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        operation = params["operation"]
        archive_path = Path(params["archive_path"]).expanduser().resolve()

        dispatch = {
            "list": self._list_contents,
            "extract": self._extract,
            "create": self._create,
            "info": self._get_info,
        }
        if operation not in dispatch:
            raise ValueError(f"Unknown operation: {operation}")

        return dispatch[operation](archive_path, params)

    def _list_contents(self, archive_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        entries: list[dict[str, Any]] = []

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    entries.append({
                        "name": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compress_size,
                        "is_dir": info.is_dir(),
                        "date_time": "%04d-%02d-%02d %02d:%02d:%02d" % info.date_time,
                    })
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    entries.append({
                        "name": member.name,
                        "size": member.size,
                        "is_dir": member.isdir(),
                        "mode": oct(member.mode) if member.mode else None,
                    })
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

        return {
            "archive": str(archive_path),
            "entries": entries,
            "count": len(entries),
        }

    def _extract(self, archive_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        output_dir = Path(params.get("output_dir") or archive_path.parent / archive_path.stem)
        output_dir.mkdir(parents=True, exist_ok=True)
        selected_files = params.get("files")
        extracted: list[str] = []

        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, "r") as zf:
                members = selected_files or [m.filename for m in zf.infolist()]
                for name in members:
                    try:
                        zf.extract(name, output_dir)
                        extracted.append(name)
                    except KeyError:
                        pass
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as tf:
                if selected_files:
                    for name in selected_files:
                        try:
                            member = tf.getmember(name)
                            tf.extract(member, output_dir, filter="data")
                            extracted.append(name)
                        except KeyError:
                            pass
                else:
                    tf.extractall(output_dir, filter="data")
                    extracted = [m.name for m in tf.getmembers()]
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

        return {
            "archive": str(archive_path),
            "output_dir": str(output_dir),
            "extracted": extracted,
            "count": len(extracted),
        }

    def _create(self, archive_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        files = params.get("files")
        if not files:
            raise ValueError("'files' parameter is required for create operation")

        fmt = params.get("format")
        if not fmt:
            suffix = "".join(archive_path.suffixes).lower()
            fmt_map = {
                ".zip": "zip",
                ".tar": "tar",
                ".tar.gz": "tar.gz",
                ".tgz": "tar.gz",
                ".tar.bz2": "tar.bz2",
                ".tar.xz": "tar.xz",
            }
            fmt = fmt_map.get(suffix, "zip")

        archive_path.parent.mkdir(parents=True, exist_ok=True)
        added: list[str] = []

        if fmt == "zip":
            comp_level = params.get("compression_level", 6)
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=comp_level) as zf:
                for file_path in files:
                    p = Path(file_path).expanduser().resolve()
                    if p.is_file():
                        zf.write(p, p.name)
                        added.append(p.name)
                    elif p.is_dir():
                        for child in p.rglob("*"):
                            if child.is_file():
                                arcname = str(child.relative_to(p.parent))
                                zf.write(child, arcname)
                                added.append(arcname)
        else:
            mode_map = {"tar": "w", "tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz"}
            mode = mode_map.get(fmt, "w:gz")
            with tarfile.open(archive_path, mode) as tf:
                for file_path in files:
                    p = Path(file_path).expanduser().resolve()
                    if p.exists():
                        tf.add(p, arcname=p.name)
                        added.append(p.name)

        return {
            "archive": str(archive_path),
            "format": fmt,
            "files_added": added,
            "count": len(added),
            "size": archive_path.stat().st_size,
        }

    def _get_info(self, archive_path: Path, params: dict[str, Any]) -> dict[str, Any]:
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        archive_size = archive_path.stat().st_size
        file_count = 0
        dir_count = 0
        total_uncompressed = 0

        if zipfile.is_zipfile(archive_path):
            fmt = "zip"
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        dir_count += 1
                    else:
                        file_count += 1
                        total_uncompressed += info.file_size
        elif tarfile.is_tarfile(archive_path):
            fmt = "tar"
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    if member.isdir():
                        dir_count += 1
                    else:
                        file_count += 1
                        total_uncompressed += member.size
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

        ratio = 0.0
        if total_uncompressed > 0:
            ratio = round(1.0 - archive_size / total_uncompressed, 4)

        return {
            "archive": str(archive_path),
            "format": fmt,
            "archive_size": archive_size,
            "uncompressed_size": total_uncompressed,
            "compression_ratio": ratio,
            "file_count": file_count,
            "dir_count": dir_count,
        }
