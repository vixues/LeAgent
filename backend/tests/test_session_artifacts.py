from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from leagent.agent.deps import QueryDeps
from leagent.agent.query import ToolResultMessage
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
from leagent.services.session.artifacts import (
    ArtifactRegistrar,
    extract_produced_path_candidates,
    ingest_previewable_produced_files,
    is_previewable_produced_file,
    strip_inline_base64_payloads,
)
from leagent.tools.base import ToolContext


class _FakeSessionManager:
    async def register_external_file(
        self,
        session_id,
        user_id,
        source_path: str,
        *,
        display_name: str | None = None,
        allowed_roots=None,
    ) -> dict[str, Any] | None:
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            return None
        file_id = uuid4()
        storage = self.storage_dir / f"{file_id}_{path.name}"
        storage.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, storage)
        self.calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "source_path": str(path),
                "display_name": display_name,
                "allowed_roots": tuple(str(Path(r).resolve()) for r in (allowed_roots or ())),
            }
        )
        return {
            "id": str(file_id),
            "filename": display_name or path.name,
            "name": display_name or path.name,
            "kind": "image" if path.suffix in {".png", ".gif"} else "text",
            "content_type": "image/png" if path.suffix == ".png" else "image/gif",
            "size": path.stat().st_size,
            "sha256": "fake-sha256",
            "storage_path": str(storage),
            "preview_url": f"/api/v1/files/{file_id}/preview?token=signed",
            "download_url": f"/api/v1/files/{file_id}/download?token=signed",
        }

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.storage_dir = storage_dir or Path("/tmp/fake-uploads")


def test_extracts_workspace_relative_and_file_uri_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    rel_out = workspace / "chart.png"
    rel_out.write_text("png", encoding="utf-8")
    uri_out = tmp_path / "report.txt"
    uri_out.write_text("report", encoding="utf-8")

    candidates = extract_produced_path_candidates(
        {
            "workspace": str(workspace),
            "produced_files": [{"path": "chart.png", "mime": "image/png"}],
            "artifact": {"uri": f"file://{uri_out}", "name": "report.txt"},
        }
    )

    by_name = {Path(c.path).name: c for c in candidates}
    assert by_name["chart.png"].allowed_root == str(workspace.resolve())
    assert by_name["report.txt"].allowed_root is None


def test_is_previewable_produced_file(tmp_path: Path) -> None:
    gif = tmp_path / "spin.gif"
    gif.write_bytes(b"GIF89a")
    csv = tmp_path / "data.csv"
    csv.write_text("a,b", encoding="utf-8")
    assert is_previewable_produced_file(gif)
    assert not is_previewable_produced_file(csv)


def test_extract_skips_already_managed_produced_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    managed = workspace / "chart.png"
    managed.write_text("png", encoding="utf-8")

    candidates = extract_produced_path_candidates(
        {
            "workspace": str(workspace),
            "produced_files": [
                {"path": "chart.png", "file_id": "already-registered"},
                {"path": str(managed)},
            ],
        }
    )
    assert len(candidates) == 1
    assert Path(candidates[0].path).name == "chart.png"


def test_extract_skips_managed_entries_in_files_array(tmp_path: Path) -> None:
    """Stale ``files`` mirrors must not re-register already-ingested outputs."""
    tmp_out = Path("/tmp/matlab_logo_interactive.html")
    managed_path = tmp_path / "uploads" / "matlab_logo_interactive.html"
    managed_path.parent.mkdir(parents=True)
    managed_path.write_text("<html></html>", encoding="utf-8")

    candidates = extract_produced_path_candidates(
        {
            "workspace": str(tmp_path / "ws"),
            "produced_files": [
                {
                    "path": str(managed_path),
                    "file_path": str(managed_path),
                    "file_id": "registered-id",
                    "managed": True,
                    "source_path": str(tmp_out),
                }
            ],
            "files": [
                {
                    "path": str(tmp_out),
                    "file_path": str(tmp_out),
                    "managed": True,
                    "file_id": "registered-id",
                }
            ],
        }
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_ingest_previewable_produced_files_registers_outside_uploads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gif = tmp_path / "3d_rotation.gif"
    gif.write_bytes(b"GIF89a")
    manager = _FakeSessionManager(storage_dir=tmp_path / "uploads")
    session_id = uuid4()
    user_id = uuid4()
    ctx = ToolContext(user_id=str(user_id), session_id=str(session_id))

    monkeypatch.setattr(
        "leagent.main.get_service_manager",
        lambda: SimpleNamespace(session_manager=manager),
    )

    produced, managed = await ingest_previewable_produced_files(
        ctx,
        [{"path": str(gif), "mime": "image/gif"}],
        workspace=str(tmp_path / "ws"),
    )

    assert len(manager.calls) == 1
    assert manager.calls[0]["source_path"] == str(gif.resolve())
    assert produced[0]["file_id"]
    assert produced[0]["managed"] is True
    assert Path(produced[0]["path"]).is_file()
    assert managed[0]["preview_url"].startswith("/api/v1/files/")


@pytest.mark.asyncio
async def test_ingest_skips_entries_with_existing_file_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _FakeSessionManager()
    ctx = ToolContext(user_id=str(uuid4()), session_id=str(uuid4()))
    monkeypatch.setattr(
        "leagent.main.get_service_manager",
        lambda: SimpleNamespace(session_manager=manager),
    )

    produced, managed = await ingest_previewable_produced_files(
        ctx,
        [{"path": str(tmp_path / "x.png"), "file_id": "existing"}],
    )

    assert manager.calls == []
    assert produced[0]["file_id"] == "existing"
    assert managed == []


def test_strip_inline_base64_payloads_recursively() -> None:
    payload = {
        "produced_files": [{"path": "plot.gif", "base64": "huge"}],
        "images": [{"path": "plot.gif", "content_base64": "huge"}],
        "nested": {"b64_json": "huge", "keep": "ok"},
    }

    assert strip_inline_base64_payloads(payload) == {
        "produced_files": [{"path": "plot.gif"}],
        "images": [{"path": "plot.gif"}],
        "nested": {"keep": "ok"},
    }


@pytest.mark.asyncio
async def test_registrar_returns_managed_attachment_payload(tmp_path: Path) -> None:
    output = tmp_path / "paper_airplane_flowchart.png"
    output.write_text("png", encoding="utf-8")
    manager = _FakeSessionManager()
    registrar = ArtifactRegistrar(manager)
    session_id = uuid4()
    user_id = uuid4()

    registered = await registrar.register_tool_result(
        session_id=session_id,
        user_id=user_id,
        data={"result": {"saved_to": str(output)}},
        seen_paths=set(),
    )

    assert len(registered) == 1
    assert manager.calls[0]["display_name"] == "paper_airplane_flowchart.png"
    assert registered[0].attachment["preview_url"].startswith("/api/v1/files/")
    assert "sha256" in registered[0].attachment
    assert "/paper_airplane_flowchart/" not in registered[0].attachment["preview_url"]


@pytest.mark.asyncio
async def test_query_engine_emits_workspace_attachments_for_tool_outputs(tmp_path: Path) -> None:
    output = tmp_path / "plot.png"
    output.write_text("png", encoding="utf-8")
    manager = _FakeSessionManager()

    async def call_model(**_kwargs):
        if False:
            yield None

    async def microcompact(messages, _ctx):
        return messages

    async def autocompact(messages, _ctx, _system_prompt=""):
        return messages

    engine = QueryEngine(
        QueryEngineConfig(
            deps=QueryDeps(call_model=call_model, microcompact=microcompact, autocompact=autocompact),
            session_manager=manager,
            session_id=uuid4(),
            user_id=uuid4(),
        )
    )

    messages = [
        msg
        async for msg in engine._map_item(
            ToolResultMessage(
                tool_call_id="call_1",
                name="code_execution",
                content="{}",
                success=True,
                envelope={"data": {"produced_files": [{"path": str(output)}]}, "metadata": {}},
            )
        )
    ]

    assert [m.type for m in messages] == ["workspace_attachments", "tool_result"]
    assert messages[0].data["attachments"][0]["preview_url"].startswith("/api/v1/files/")
    payload = json.loads(messages[1].data["content"])
    assert payload["managed_artifacts"][0]["preview_url"].startswith("/api/v1/files/")
