"""Workflow-scoped artifact registration (no session_id, with user_id)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.file.service import FileService
from leagent.file.storage.local import LocalStorageBackend
from leagent.file.tool_output import register_tool_artifact


@pytest.mark.asyncio
async def test_register_tool_artifact_without_session_returns_signed_urls(
    tmp_path, monkeypatch,
) -> None:
    """Editor workflow runs have user_id but no session — previews need signed URLs."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    fs = FileService(
        default_backend=LocalStorageBackend(uploads),
        default_backend_name="local",
    )

    class _FakeSM:
        file_service = fs

    monkeypatch.setattr(
        "leagent.services.service_manager.get_service_manager",
        lambda: _FakeSM(),
    )

    user_id = uuid4()
    attachment = await register_tool_artifact(
        b"\x89PNG\r\n\x1a\n",
        filename="workflow-artifact.png",
        content_type="image/png",
        session_id=None,
        user_id=user_id,
    )
    assert attachment is not None
    assert attachment.get("preview_url", "").startswith("/api/v1/files/")
    assert "token=" in attachment.get("preview_url", "")
    assert attachment.get("download_url", "").startswith("/api/v1/files/")
