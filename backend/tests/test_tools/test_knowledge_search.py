"""Tests for the progressive knowledge_search tool."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from leagent.config.settings import Settings
from leagent.db.models.file import File, FileStatus, FileType, LibraryScope
from leagent.db.models.identity_stub import UserStub
from leagent.db.service import DatabaseService
from leagent.library.chunking import chunk_text
from leagent.services.auth.service import LOCAL_USER_ID
from leagent.tools.base import SyncTool, ToolCategory, ToolContext, ToolResult
from leagent.tools.doc.knowledge_search import KnowledgeSearchTool
from leagent.tools.registry import ToolRegistry


@pytest.fixture()
async def kb_db(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "kb.db"
        monkeypatch.setenv("DB_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
        settings = Settings()
        db = DatabaseService(settings)
        await db.create_tables()
        monkeypatch.setattr("leagent.db.get_database_service", lambda: db)
        yield db
        await db.dispose()


async def _add_knowledge_file(
    db: DatabaseService,
    *,
    user_id,
    name: str,
    text: str,
    summary: str | None = None,
) -> File:
    fid = uuid4()
    row = File(
        id=fid,
        user_id=user_id,
        name=name,
        original_name=name,
        file_type=FileType.DOCUMENT,
        size=len(text),
        status=FileStatus.PROCESSED,
        storage_path=f"/tmp/{name}",
        extracted_text=text,
        summary=summary,
        is_indexed=True,
        library_scope=LibraryScope.KNOWLEDGE,
    )
    async with db.session() as session:
        session.add(row)
    chunks = chunk_text(text)
    await db.repositories.document_chunks.replace_for_file(fid, user_id, chunks)
    return row


@pytest.mark.asyncio
async def test_catalog_empty(kb_db: DatabaseService) -> None:
    tool = KnowledgeSearchTool()
    ctx = ToolContext(user_id=str(LOCAL_USER_ID), session_id=None)
    result = await tool.execute({"action": "catalog"}, ctx)
    assert result["total"] == 0
    assert result["documents"] == []
    assert "empty" in result["hint"].lower()


@pytest.mark.asyncio
async def test_catalog_search_read_and_lazy_summary(kb_db: DatabaseService) -> None:
    tool = KnowledgeSearchTool()
    text = (
        "# Refund Policy\n\n"
        "Customers may request a refund within 30 days of purchase. "
        "Digital goods are non-refundable after download.\n\n"
        "Contact support for exceptions."
    )
    row = await _add_knowledge_file(
        kb_db, user_id=LOCAL_USER_ID, name="refund.md", text=text, summary=None
    )
    ctx = ToolContext(user_id=str(LOCAL_USER_ID), session_id=None)

    catalog = await tool.execute({"action": "catalog"}, ctx)
    assert catalog["total"] == 1
    doc = catalog["documents"][0]
    assert doc["file_id"] == str(row.id)
    assert doc["summary"]
    assert "Refund" in doc["summary"]

    search = await tool.execute(
        {"action": "search", "query": "refund", "limit": 5},
        ctx,
    )
    assert search["total"] >= 1
    hit = search["results"][0]
    assert hit["file_id"] == str(row.id)

    read = await tool.execute(
        {
            "action": "read",
            "file_id": str(row.id),
            "start_offset": hit["start_offset"],
            "end_offset": hit["end_offset"],
        },
        ctx,
    )
    assert read["file_id"] == str(row.id)
    assert "refund" in read["text"].lower()
    assert read["summary"]


@pytest.mark.asyncio
async def test_ownership_isolation(kb_db: DatabaseService) -> None:
    tool = KnowledgeSearchTool()
    other = uuid4()
    async with kb_db.session() as session:
        session.add(UserStub(id=other))

    row = await _add_knowledge_file(
        kb_db,
        user_id=LOCAL_USER_ID,
        name="secret.md",
        text="Confidential payroll numbers live here.",
        summary="Confidential payroll",
    )

    other_ctx = ToolContext(user_id=str(other), session_id=None)
    catalog = await tool.execute({"action": "catalog"}, other_ctx)
    assert catalog["total"] == 0

    search = await tool.execute(
        {"action": "search", "query": "payroll"},
        other_ctx,
    )
    assert search["total"] == 0

    read = await tool.execute({"action": "read", "file_id": str(row.id)}, other_ctx)
    assert "error" in read


@pytest.mark.asyncio
async def test_read_requires_extracted_text(kb_db: DatabaseService) -> None:
    tool = KnowledgeSearchTool()
    fid = uuid4()
    async with kb_db.session() as session:
        session.add(
            File(
                id=fid,
                user_id=LOCAL_USER_ID,
                name="empty.pdf",
                original_name="empty.pdf",
                file_type=FileType.DOCUMENT,
                size=1,
                status=FileStatus.PROCESSED,
                storage_path="/tmp/empty.pdf",
                extracted_text=None,
                is_indexed=False,
                library_scope=LibraryScope.KNOWLEDGE,
            )
        )
    ctx = ToolContext(user_id=str(LOCAL_USER_ID), session_id=None)
    result = await tool.execute({"action": "read", "file_id": str(fid)}, ctx)
    assert "error" in result
    assert "extracted text" in result["error"]


def test_knowledge_hint_forces_tool_into_pool() -> None:
    class _Filler(SyncTool):
        description = "irrelevant filler"
        category = ToolCategory.UTIL
        version = "1.0.0"

        def __init__(self, name: str) -> None:
            self.name = name

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}}

        def execute_sync(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
            return ToolResult.ok({})

    reg = ToolRegistry()
    for idx in range(30):
        reg.register(_Filler(f"aaa_filler_{idx:02d}"))
    reg.register(KnowledgeSearchTool())

    schemas = reg.get_tools_for_llm(
        provider_format="openai",
        context_hint="请根据知识库里的文档回答退款政策",
        max_tools=5,
    )
    names = {schema["function"]["name"] for schema in schemas}
    assert "knowledge_search" in names
