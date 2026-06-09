"""Tests for GET /api/v1/chat/sessions/{id}/attachments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from leagent.services.auth.deps import get_current_user_id
from leagent.services.chat.service import get_chat_service
from leagent.db.models.message import ChatSession
from leagent.services.session.state import SessionAttachment


def _session_for_user(session_id: UUID, user_id: UUID) -> ChatSession:
    now = datetime.utcnow()
    return ChatSession(
        id=session_id,
        user_id=user_id,
        name="t",
        is_active=True,
        message_count=0,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
class TestSessionAttachmentsEndpoint:
    async def test_404_when_session_missing(
        self,
        async_client: Any,
        test_user: dict[str, Any],
        app: Any,
    ) -> None:
        uid = UUID(test_user["user_id"])

        async def _user_id() -> UUID:
            return uid

        mock_chat = MagicMock()
        mock_chat.get_session = AsyncMock(return_value=None)
        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            sid = uuid4()
            resp = await async_client.get(f"/api/v1/chat/sessions/{sid}/attachments")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404

    async def test_lists_attachments_from_session_manager(
        self,
        async_client: Any,
        test_user: dict[str, Any],
        app: Any,
    ) -> None:
        uid = UUID(test_user["user_id"])
        sid = uuid4()
        aid = uuid4()
        mock_chat = MagicMock()
        mock_chat.get_session = AsyncMock(return_value=_session_for_user(sid, uid))

        att = SessionAttachment(
            id=aid,
            session_id=sid,
            filename="out.txt",
            storage_path="/tmp/out.txt",
            content_type="text/plain",
            kind="text",
            size=4,
            sha256="0" * 64,
            created_at=datetime.now(timezone.utc),
            preview_url="/api/v1/files/preview",
            download_url="/api/v1/files/dl",
            extra={"source_tool_path": "/workspace/out.txt"},
        )

        session_manager = MagicMock()
        session_manager.list_attachments = AsyncMock(return_value=[att])

        sm = MagicMock()
        sm.session_manager = session_manager

        async def _user_id() -> UUID:
            return uid

        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            with patch("leagent.main.get_service_manager", return_value=sm):
                resp = await async_client.get(f"/api/v1/chat/sessions/{sid}/attachments")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == str(sid)
        assert len(body["attachments"]) == 1
        row = body["attachments"][0]
        assert row["id"] == str(aid)
        assert row["name"] == "out.txt"
        assert row["filename"] == "out.txt"
