"""Unified file processing service.

Auto-detects file type by MIME/extension and delegates to the appropriate
tool for text extraction. Updates File.status through the processing pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EXTENSION_HANDLER_MAP: dict[str, str] = {
    ".pdf": "pdf_reader",
    ".doc": "word_reader",
    ".docx": "word_reader",
    ".xls": "excel_reader",
    ".xlsx": "excel_reader",
    ".csv": "csv_processor",
    ".tsv": "csv_processor",
    ".md": "markdown_processor",
    ".markdown": "markdown_processor",
    ".html": "html_processor",
    ".htm": "html_processor",
    ".json": "config_file",
    ".yaml": "config_file",
    ".yml": "config_file",
    ".toml": "config_file",
    ".txt": "text_processor",
    ".log": "text_processor",
    ".cfg": "text_processor",
    ".ini": "text_processor",
    ".py": "text_processor",
    ".js": "text_processor",
    ".ts": "text_processor",
    ".java": "text_processor",
    ".c": "text_processor",
    ".cpp": "text_processor",
    ".h": "text_processor",
    ".rs": "text_processor",
    ".go": "text_processor",
    ".rb": "text_processor",
    ".sh": "text_processor",
    ".sql": "text_processor",
    ".xml": "text_processor",
    ".css": "text_processor",
    ".zip": "archive_manager",
    ".tar": "archive_manager",
    ".gz": "archive_manager",
    ".bz2": "archive_manager",
    ".xz": "archive_manager",
    ".tgz": "archive_manager",
    ".png": "image_ocr",
    ".jpg": "image_ocr",
    ".jpeg": "image_ocr",
    ".tiff": "image_ocr",
    ".bmp": "image_ocr",
}


class FileProcessingService:
    """Service that auto-processes uploaded files to extract text and metadata."""

    def __init__(self) -> None:
        self._started = True

    async def process_file(
        self,
        file_path: str,
        mime_type: str | None = None,
        original_name: str | None = None,
    ) -> dict[str, Any]:
        """Process a file and extract text content.

        Returns a dict with 'extracted_text', 'metadata', and 'handler' keys.
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}", "extracted_text": None}

        handler_name = self._resolve_handler(path, mime_type, original_name)
        if not handler_name:
            return {
                "extracted_text": None,
                "handler": None,
                "message": "No handler available for this file type",
            }

        try:
            result = await self._run_handler(handler_name, path)
            text = self._extract_text_from_result(handler_name, result)
            return {
                "extracted_text": text,
                "metadata": result,
                "handler": handler_name,
            }
        except Exception as exc:
            logger.warning("File processing failed: %s", exc, exc_info=True)
            return {
                "extracted_text": None,
                "handler": handler_name,
                "error": str(exc),
            }

    def _resolve_handler(
        self,
        path: Path,
        mime_type: str | None,
        original_name: str | None,
    ) -> str | None:
        ext = path.suffix.lower()
        if not ext and original_name:
            ext = Path(original_name).suffix.lower()

        handler = EXTENSION_HANDLER_MAP.get(ext)
        if handler:
            return handler

        if mime_type:
            mime_ext_map = {
                "application/pdf": "pdf_reader",
                "application/msword": "word_reader",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word_reader",
                "application/vnd.ms-excel": "excel_reader",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel_reader",
                "text/csv": "csv_processor",
                "text/markdown": "markdown_processor",
                "text/html": "html_processor",
                "application/json": "config_file",
                "text/plain": "text_processor",
                "application/zip": "archive_manager",
                "application/x-tar": "archive_manager",
                "image/png": "image_ocr",
                "image/jpeg": "image_ocr",
            }
            return mime_ext_map.get(mime_type)

        return None

    async def _run_handler(self, handler_name: str, path: Path) -> dict[str, Any]:
        from leagent.tools.registry import get_registry
        from leagent.tools.base import ToolContext

        registry = get_registry()
        tool = registry.get(handler_name)
        if tool is None:
            raise RuntimeError(f"Tool '{handler_name}' not found in registry")

        ctx = ToolContext(user_id=None, session_id=None, task_id=None)

        if handler_name == "archive_manager":
            params = {"operation": "info", "archive_path": str(path)}
        elif handler_name in ("csv_processor", "text_processor", "markdown_processor", "html_processor"):
            params = {"operation": "read", "file_path": str(path)}
        elif handler_name == "config_file":
            params = {"operation": "read", "file_path": str(path)}
        elif handler_name == "image_ocr":
            params = {"image_path": str(path)}
        elif handler_name in ("pdf_reader", "word_reader", "excel_reader"):
            params = {"file_path": str(path)}
        else:
            params = {"file_path": str(path)}

        result = await tool.run(params, ctx)
        return result.data if hasattr(result, "data") else result

    def _extract_text_from_result(self, handler_name: str, result: dict[str, Any]) -> str | None:
        if not isinstance(result, dict):
            return None

        for key in ("text", "extracted_text", "raw_text", "content"):
            if key in result and isinstance(result[key], str):
                return result[key][:500_000]

        if "data" in result and isinstance(result["data"], dict):
            return self._extract_text_from_result(handler_name, result["data"])

        return None

    async def process_and_update_db(
        self,
        file_id: str,
        file_path: str,
        mime_type: str | None = None,
        original_name: str | None = None,
    ) -> dict[str, Any]:
        """Process a file and update the database File record."""
        from uuid import UUID
        from datetime import datetime
        from leagent.services.service_manager import get_service_manager
        from leagent.services.database.models.file import FileStatus

        result = await self.process_file(file_path, mime_type, original_name)

        sm = get_service_manager()
        if sm.db is None:
            return result

        try:
            from sqlalchemy import text
            from leagent.services.database.models.file import File
            from leagent.services.database.sqlite_compat import sqlite_parent_id_text

            async with sm.db.session() as session:
                bind = session.get_bind()
                dialect = getattr(getattr(bind, "dialect", None), "name", "") or ""
                logical = UUID(file_id)
                if dialect == "sqlite":
                    id_txt = await sqlite_parent_id_text(session, "files", logical)
                    now = datetime.utcnow()
                    if result.get("extracted_text"):
                        st = FileStatus.PROCESSED.name
                        await session.execute(
                            text(
                                "UPDATE files SET extracted_text=:xt, status=:st, updated_at=:u "
                                "WHERE CAST(id AS TEXT) = :id"
                            ),
                            {
                                "xt": result["extracted_text"],
                                "st": st,
                                "u": now,
                                "id": id_txt,
                            },
                        )
                    elif result.get("error"):
                        await session.execute(
                            text(
                                "UPDATE files SET status=:st, updated_at=:u "
                                "WHERE CAST(id AS TEXT) = :id"
                            ),
                            {"st": FileStatus.FAILED.name, "u": now, "id": id_txt},
                        )
                    else:
                        await session.execute(
                            text(
                                "UPDATE files SET status=:st, updated_at=:u "
                                "WHERE CAST(id AS TEXT) = :id"
                            ),
                            {"st": FileStatus.PROCESSED.name, "u": now, "id": id_txt},
                        )
                else:
                    f = await session.get(File, logical)
                    if f:
                        if result.get("extracted_text"):
                            f.extracted_text = result["extracted_text"]
                            f.status = FileStatus.PROCESSED
                        elif result.get("error"):
                            f.status = FileStatus.FAILED
                        else:
                            f.status = FileStatus.PROCESSED
                        f.updated_at = datetime.utcnow()
                        session.add(f)
        except Exception as exc:
            logger.warning("Failed to update file record: %s", exc)

        return result
