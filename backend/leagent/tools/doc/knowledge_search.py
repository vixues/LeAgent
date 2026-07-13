"""Progressive knowledge-base tool: catalog → search → read.

Does not inject KB content into the system prompt. The agent enables this
path by calling the tool when the turn looks knowledge-related (tool pool
scoring + a one-line capabilities ad). Explicit ``@knowledge:`` attachments
remain a shortcut for whole-file mounts.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlmodel import col, select

from leagent.db.models.file import File, LibraryScope
from leagent.library.summary import summarize_extracted_text
from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.context import resolve_effective_user_id

logger = structlog.get_logger(__name__)

_DEFAULT_SEARCH_LIMIT = 8
_MAX_SEARCH_LIMIT = 20
_DEFAULT_READ_CHARS = 8000
_MAX_READ_CHARS = 32_000
_MAX_CATALOG = 100


def _pet_project_library_file_ids_subquery(user_id: UUID):
    from leagent.db.models import PetProject, PetProjectFile

    return (
        select(PetProjectFile.file_id)
        .join(PetProject, PetProjectFile.pet_project_id == PetProject.id)
        .where(
            PetProject.user_id == user_id,
            PetProject.is_deleted == False,  # noqa: E712
        )
    )


class KnowledgeSearchTool(BaseTool):
    """User knowledge base: catalog summaries, BM25 search, then read text windows."""

    name = "knowledge_search"
    description = (
        "User knowledge base (catalog → search → read). "
        "Call action=catalog first for document summaries, then action=search with a query, "
        "then action=read with file_id (and optional offsets) for extracted text. "
        "Do not invent document contents. If the user already @knowledge-attached a file, "
        "prefer existing document readers on that path instead."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 30
    is_read_only = True
    is_concurrency_safe = True
    capabilities = (ToolCapability.FILE_READ,)
    search_hint = (
        "knowledge kb 知识库 文档库 资料 查阅 document library catalog search "
        "根据文档 参考文档 查阅资料"
    )
    max_result_size_chars = 50_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["action"],
            "additionalProperties": False,
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["catalog", "search", "read"],
                    "description": (
                        "catalog: list KB docs with summaries; "
                        "search: BM25 over indexed chunks (requires query); "
                        "read: extracted text window (requires file_id)."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": "Search query (required for action=search).",
                    "minLength": 1,
                    "maxLength": 1000,
                },
                "file_id": {
                    "type": "string",
                    "description": "Knowledge file UUID (required for action=read).",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max search hits (1–{_MAX_SEARCH_LIMIT}, default {_DEFAULT_SEARCH_LIMIT}).",
                    "minimum": 1,
                    "maximum": _MAX_SEARCH_LIMIT,
                },
                "start_offset": {
                    "type": "integer",
                    "description": "Inclusive start offset into extracted_text (action=read).",
                    "minimum": 0,
                },
                "end_offset": {
                    "type": "integer",
                    "description": "Exclusive end offset into extracted_text (action=read).",
                    "minimum": 0,
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        f"Max characters to return from start_offset when end_offset "
                        f"is omitted (default {_DEFAULT_READ_CHARS}, max {_MAX_READ_CHARS})."
                    ),
                    "minimum": 1,
                    "maximum": _MAX_READ_CHARS,
                },
            },
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        action = (params or {}).get("action") or "catalog"
        if action == "search":
            q = (params or {}).get("query") or ""
            return f"Searching knowledge base{f' for {q!r}' if q else ''}"
        if action == "read":
            return "Reading knowledge document"
        return "Listing knowledge base"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        action = str(params.get("action") or "").strip()
        if action not in ("catalog", "search", "read"):
            return {"error": "action must be catalog, search, or read"}

        from leagent.db import get_database_service

        user_id = resolve_effective_user_id(context.user_id, session_id=context.session_id)
        if user_id is None:
            return {"error": "user_id required to access knowledge base", "action": action}

        db = get_database_service()

        if action == "catalog":
            return await self._catalog(db, user_id)
        if action == "search":
            query = str(params.get("query") or "").strip()
            if not query:
                return {"error": "query is required for action=search", "action": action}
            limit = int(params.get("limit") or _DEFAULT_SEARCH_LIMIT)
            limit = max(1, min(limit, _MAX_SEARCH_LIMIT))
            return await self._search(db, user_id, query, limit=limit)
        return await self._read(db, user_id, params)

    async def _ensure_summary(self, db: Any, row: File) -> str | None:
        if row.summary:
            return row.summary
        if not row.extracted_text:
            return None
        summary = summarize_extracted_text(row.extracted_text)
        if summary is None:
            return None
        try:
            async with db.session() as session:
                fresh = await session.get(File, row.id)
                if fresh is not None and not fresh.summary:
                    fresh.summary = summary
                    session.add(fresh)
            row.summary = summary
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge_summary_lazy_write_failed", error=str(exc), file_id=str(row.id))
        return summary

    async def _catalog(self, db: Any, user_id: UUID) -> dict[str, Any]:
        pet_lib = _pet_project_library_file_ids_subquery(user_id)
        async with db.session() as session:
            stmt = (
                select(File)
                .where(
                    File.user_id == user_id,
                    File.is_deleted == False,  # noqa: E712
                    File.library_scope == LibraryScope.KNOWLEDGE,
                    ~File.id.in_(pet_lib),
                )
                .order_by(col(File.created_at).desc())
                .limit(_MAX_CATALOG)
            )
            rows = list((await session.exec(stmt)).all())

        documents: list[dict[str, Any]] = []
        for row in rows:
            summary = await self._ensure_summary(db, row)
            documents.append(
                {
                    "file_id": str(row.id),
                    "name": row.original_name or row.name,
                    "file_type": row.file_type.value if hasattr(row.file_type, "value") else str(row.file_type),
                    "is_indexed": bool(row.is_indexed),
                    "summary": summary,
                }
            )

        if not documents:
            return {
                "action": "catalog",
                "total": 0,
                "documents": [],
                "hint": "Knowledge base is empty. Ask the user to upload documents or promote chat files.",
            }
        return {
            "action": "catalog",
            "total": len(documents),
            "documents": documents,
            "hint": "Next: action=search with a focused query, then action=read for needed file_id windows.",
        }

    async def _search(
        self,
        db: Any,
        user_id: UUID,
        query: str,
        *,
        limit: int,
    ) -> dict[str, Any]:
        hits = await db.repositories.document_chunks.search(
            user_id,
            query,
            limit=limit,
            library_scope=LibraryScope.KNOWLEDGE.value,
        )
        results: list[dict[str, Any]] = []
        for hit in hits:
            async with db.session() as session:
                f = await session.get(File, hit.file_id)
                if f is None or f.is_deleted or f.user_id != user_id:
                    continue
                if f.library_scope != LibraryScope.KNOWLEDGE:
                    continue
            results.append(
                {
                    "file_id": str(hit.file_id),
                    "name": hit.file_name,
                    "score": hit.score,
                    "snippet": hit.snippet,
                    "chunk_id": str(hit.chunk_id),
                    "start_offset": hit.start_offset,
                    "end_offset": hit.end_offset,
                }
            )

        return {
            "action": "search",
            "query": query,
            "total": len(results),
            "results": results,
            "hint": (
                "Use action=read with file_id and start_offset/end_offset from a hit "
                "to load the matching text window."
                if results
                else "No chunk matches. Try action=catalog or a broader query."
            ),
        }

    async def _read(self, db: Any, user_id: UUID, params: dict[str, Any]) -> dict[str, Any]:
        raw_id = str(params.get("file_id") or "").strip()
        if not raw_id:
            return {"error": "file_id is required for action=read", "action": "read"}
        try:
            file_id = UUID(raw_id)
        except (TypeError, ValueError):
            return {"error": f"invalid file_id: {raw_id}", "action": "read"}

        async with db.session() as session:
            row = await session.get(File, file_id)

        if (
            row is None
            or row.is_deleted
            or row.user_id != user_id
            or row.library_scope != LibraryScope.KNOWLEDGE
        ):
            return {
                "error": "file not found in your knowledge base",
                "action": "read",
                "file_id": raw_id,
            }

        text = row.extracted_text
        if not text or not str(text).strip():
            return {
                "error": "no extracted text available; file may still be processing or unsupported",
                "action": "read",
                "file_id": str(row.id),
                "name": row.original_name or row.name,
                "is_indexed": bool(row.is_indexed),
            }

        start = int(params.get("start_offset") or 0)
        start = max(0, min(start, len(text)))
        end_raw = params.get("end_offset")
        if end_raw is not None:
            end = int(end_raw)
            end = max(start, min(end, len(text)))
        else:
            max_chars = int(params.get("max_chars") or _DEFAULT_READ_CHARS)
            max_chars = max(1, min(max_chars, _MAX_READ_CHARS))
            end = min(len(text), start + max_chars)

        summary = await self._ensure_summary(db, row)
        window = text[start:end]
        truncated = end < len(text)

        return {
            "action": "read",
            "file_id": str(row.id),
            "name": row.original_name or row.name,
            "summary": summary,
            "start_offset": start,
            "end_offset": end,
            "total_chars": len(text),
            "truncated": truncated,
            "text": window,
            "hint": (
                "Increase start_offset or call again with a later window if truncated."
                if truncated
                else None
            ),
        }
