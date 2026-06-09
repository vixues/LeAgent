"""Folder Operations Tool — agent-facing folder management via database."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class FolderOperationsTool(BaseTool):
    """Manage virtual folders for organising files, flows, and documents.

    All operations go through the database Folder/File models so changes
    are immediately visible in the REST API and frontend.
    """

    name = "folder_operations"
    description = (
        "Manage virtual folders: create, list, get tree, move, "
        "add/remove files, search folders, list files in a folder, "
        "and read a file's extracted text."
    )
    category = ToolCategory.UTIL
    version = "1.1.0"
    timeout_sec = 60
    aliases = ["folder", "virtual_folder", "folder_ops"]
    search_hint = "folder virtual create list tree move add remove search files read analyse"
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "list")
        return f"Folder operation ({op})"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "create_folder",
                        "list_folders",
                        "get_tree",
                        "move_folder",
                        "delete_folder",
                        "add_file_to_folder",
                        "remove_file_from_folder",
                        "search",
                        "list_files_in_folder",
                        "read_folder_file",
                    ],
                    "description": (
                        "Folder operation to perform.  Use list_files_in_folder "
                        "to enumerate files inside a folder (returns name, type, "
                        "size, storage_path and a text preview).  Use "
                        "read_folder_file with a file_id to get the full "
                        "extracted text of a file."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Folder name (for create).",
                },
                "description": {
                    "type": "string",
                    "description": "Folder description (for create).",
                },
                "folder_id": {
                    "type": "string",
                    "description": "Target folder UUID.",
                },
                "parent_id": {
                    "type": "string",
                    "description": "Parent folder UUID (null for root).",
                },
                "file_id": {
                    "type": "string",
                    "description": "File UUID for add/remove/read operations.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query string.",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from leagent.services.service_manager import get_service_manager

        sm = get_service_manager()
        if sm.db is None:
            return {"error": "Database service unavailable"}

        operation = params["operation"]
        dispatch = {
            "create_folder": self._create_folder,
            "list_folders": self._list_folders,
            "get_tree": self._get_tree,
            "move_folder": self._move_folder,
            "delete_folder": self._delete_folder,
            "add_file_to_folder": self._add_file,
            "remove_file_from_folder": self._remove_file,
            "search": self._search,
            "list_files_in_folder": self._list_files_in_folder,
            "read_folder_file": self._read_folder_file,
        }

        handler = dispatch.get(operation)
        if handler is None:
            return {"error": f"Unknown operation: {operation}"}

        try:
            return await handler(sm, params, context)
        except Exception as exc:
            logger.error("folder_operation_failed", operation=operation, error=str(exc))
            return {"error": str(exc)}

    def _user_id(self, ctx: ToolContext) -> UUID | None:
        return UUID(ctx.user_id) if ctx.user_id else None

    async def _create_folder(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        from leagent.db.models.folder import Folder

        name = params.get("name")
        if not name:
            return {"error": "'name' is required for create_folder"}

        parent_id = UUID(params["parent_id"]) if params.get("parent_id") else None

        async with sm.db.session() as session:
            folder = Folder(
                name=name,
                description=params.get("description", ""),
                parent_id=parent_id,
                user_id=self._user_id(ctx),
            )
            session.add(folder)
            await session.flush()
            await session.refresh(folder)
            return {
                "id": str(folder.id),
                "name": folder.name,
                "parent_id": str(folder.parent_id) if folder.parent_id else None,
                "created": True,
            }

    async def _list_folders(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        from sqlmodel import select
        from leagent.db.models.folder import Folder

        parent_id = UUID(params["parent_id"]) if params.get("parent_id") else None
        uid = self._user_id(ctx)

        async with sm.db.session() as session:
            stmt = select(Folder).where(Folder.is_deleted == False)  # noqa: E712
            if uid:
                stmt = stmt.where(Folder.user_id == uid)
            if parent_id is not None:
                stmt = stmt.where(Folder.parent_id == parent_id)
            else:
                stmt = stmt.where(Folder.parent_id == None)  # noqa: E711

            result = await session.exec(stmt)
            folders = result.all()
            return {
                "folders": [
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "description": f.description,
                        "parent_id": str(f.parent_id) if f.parent_id else None,
                        "file_count": f.file_count,
                        "flow_count": f.flow_count,
                    }
                    for f in folders
                ],
                "count": len(folders),
            }

    async def _get_tree(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        from sqlmodel import select
        from leagent.db.models.folder import Folder

        uid = self._user_id(ctx)

        async with sm.db.session() as session:
            stmt = select(Folder).where(Folder.is_deleted == False)  # noqa: E712
            if uid:
                stmt = stmt.where(Folder.user_id == uid)
            result = await session.exec(stmt)
            all_folders = result.all()

        by_parent: dict[str | None, list[Any]] = {}
        for f in all_folders:
            key = str(f.parent_id) if f.parent_id else None
            by_parent.setdefault(key, []).append(f)

        def build(parent_key: str | None) -> list[dict[str, Any]]:
            children = by_parent.get(parent_key, [])
            nodes = []
            for f in sorted(children, key=lambda x: x.name):
                node = {
                    "id": str(f.id),
                    "name": f.name,
                    "children": build(str(f.id)),
                    "file_count": f.file_count,
                }
                nodes.append(node)
            return nodes

        return {"tree": build(None)}

    async def _move_folder(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        folder_id = params.get("folder_id")
        if not folder_id:
            return {"error": "'folder_id' is required"}

        from leagent.db.models.folder import Folder

        new_parent = UUID(params["parent_id"]) if params.get("parent_id") else None

        async with sm.db.session() as session:
            folder = await session.get(Folder, UUID(folder_id))
            if not folder or folder.is_deleted:
                return {"error": "Folder not found"}
            folder.parent_id = new_parent
            session.add(folder)
            return {"id": str(folder.id), "new_parent_id": str(new_parent) if new_parent else None, "moved": True}

    async def _delete_folder(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        folder_id = params.get("folder_id")
        if not folder_id:
            return {"error": "'folder_id' is required"}

        from datetime import datetime
        from leagent.db.models.folder import Folder

        async with sm.db.session() as session:
            folder = await session.get(Folder, UUID(folder_id))
            if not folder or folder.is_deleted:
                return {"error": "Folder not found"}
            folder.is_deleted = True
            folder.deleted_at = datetime.utcnow()
            session.add(folder)
            return {"id": str(folder.id), "deleted": True}

    async def _add_file(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        folder_id = params.get("folder_id")
        file_id = params.get("file_id")
        if not folder_id or not file_id:
            return {"error": "'folder_id' and 'file_id' are required"}

        from leagent.db.models.file import File

        async with sm.db.session() as session:
            f = await session.get(File, UUID(file_id))
            if not f or f.is_deleted:
                return {"error": "File not found"}
            f.folder_id = UUID(folder_id)
            session.add(f)
            return {"file_id": file_id, "folder_id": folder_id, "added": True}

    async def _remove_file(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        file_id = params.get("file_id")
        if not file_id:
            return {"error": "'file_id' is required"}

        from leagent.db.models.file import File

        async with sm.db.session() as session:
            f = await session.get(File, UUID(file_id))
            if not f or f.is_deleted:
                return {"error": "File not found"}
            f.folder_id = None
            session.add(f)
            return {"file_id": file_id, "removed": True}

    async def _search(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        query = params.get("query", "")
        if not query:
            return {"error": "'query' is required for search"}

        from sqlmodel import select
        from leagent.db.models.folder import Folder

        uid = self._user_id(ctx)

        async with sm.db.session() as session:
            stmt = (
                select(Folder)
                .where(Folder.is_deleted == False)  # noqa: E712
                .where(Folder.name.contains(query))
            )
            if uid:
                stmt = stmt.where(Folder.user_id == uid)
            result = await session.exec(stmt)
            folders = result.all()
            return {
                "folders": [
                    {"id": str(f.id), "name": f.name, "description": f.description}
                    for f in folders
                ],
                "count": len(folders),
            }

    async def _list_files_in_folder(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """List all files inside a folder with metadata and text preview."""
        folder_id = params.get("folder_id")
        if not folder_id:
            return {"error": "'folder_id' is required"}

        from sqlmodel import select
        from leagent.db.models.file import File

        uid = self._user_id(ctx)

        async with sm.db.session() as session:
            stmt = (
                select(File)
                .where(File.folder_id == UUID(folder_id))
                .where(File.is_deleted == False)  # noqa: E712
            )
            if uid:
                stmt = stmt.where(File.user_id == uid)
            result = await session.exec(stmt)
            files = result.all()

        return {
            "files": [
                {
                    "id": str(f.id),
                    "name": f.original_name,
                    "file_type": f.file_type,
                    "size": f.size,
                    "storage_path": f.storage_path,
                    "status": f.status,
                    "extracted_text_preview": (f.extracted_text or "")[:1500] if f.extracted_text else None,
                }
                for f in files
            ],
            "count": len(files),
        }

    async def _read_folder_file(self, sm: Any, params: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
        """Return the full extracted text of a file (processing on demand if needed)."""
        file_id = params.get("file_id")
        if not file_id:
            return {"error": "'file_id' is required"}

        from leagent.db.models.file import File

        uid = self._user_id(ctx)

        async with sm.db.session() as session:
            f = await session.get(File, UUID(file_id))
            if not f or f.is_deleted:
                return {"error": "File not found"}
            if uid and f.user_id != uid:
                return {"error": "Access denied"}

            if f.extracted_text:
                return {
                    "id": str(f.id),
                    "name": f.original_name,
                    "storage_path": f.storage_path,
                    "extracted_text": f.extracted_text,
                }

        # Extracted text absent — process on demand
        if sm.file_processing:
            result = await sm.file_processing.process_and_update_db(
                file_id=file_id,
                file_path=f.storage_path,
                mime_type=f.mime_type,
                original_name=f.original_name,
            )
            return {
                "id": str(f.id),
                "name": f.original_name,
                "storage_path": f.storage_path,
                "extracted_text": result.get("extracted_text") or "(extraction failed)",
            }

        return {
            "id": str(f.id),
            "name": f.original_name,
            "storage_path": f.storage_path,
            "extracted_text": None,
            "error": "No extracted text and FileProcessingService unavailable",
        }
