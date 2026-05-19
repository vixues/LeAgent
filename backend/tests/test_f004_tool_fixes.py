"""Regression tests for F-004 speech_to_text + workflow notification payloads."""

from __future__ import annotations

import pytest

from leagent.tools.base import ToolContext
from leagent.tools.integration.notification import (
    NotificationTool,
    normalize_workflow_notification_params,
)
from leagent.tools.integration.speech_to_text import SpeechToTextTool
from leagent.tools.registry import ToolRegistry


@pytest.fixture
def tool_ctx() -> ToolContext:
    return ToolContext(user_id=None, session_id=None, task_id=None)


def test_normalize_admin_maps_and_skip_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEAGENT_ADMIN_WEBHOOK_URL", raising=False)
    out = normalize_workflow_notification_params(
        {"channel": "admin", "message": "alert", "severity": "medium"},
    )
    assert out["channel"] == "webhook"
    assert out["content"] == "alert"
    assert out["priority"] == "normal"
    assert out.get("_leagent_skip_notification") is True


def test_normalize_admin_uses_env_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_ADMIN_WEBHOOK_URL", "https://example.com/hook")
    out = normalize_workflow_notification_params({"channel": "admin", "message": "x"})
    assert out["webhook_url"] == "https://example.com/hook"
    assert out.get("_leagent_skip_notification") is None


@pytest.mark.asyncio
async def test_notification_run_admin_no_http(
    monkeypatch: pytest.MonkeyPatch,
    tool_ctx: ToolContext,
) -> None:
    monkeypatch.delenv("LEAGENT_ADMIN_WEBHOOK_URL", raising=False)
    tool = NotificationTool()
    res = await tool.run({"channel": "admin", "message": "hello"}, tool_ctx)
    assert res.success is True
    assert res.data is not None
    assert res.data.get("skipped") is True


@pytest.mark.asyncio
async def test_speech_to_text_placeholder(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    tool_ctx: ToolContext,
) -> None:
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    audio = tmp_path / "meet.wav"
    audio.write_bytes(b"fake")

    tool = SpeechToTextTool()
    res = await tool.run({"audio_file": str(audio), "language": "zh-CN"}, tool_ctx)
    assert res.success is True
    assert res.data["confidence"] == pytest.approx(0.9)
    assert "text" in res.data
    assert res.data["source"] == "placeholder"


def test_registry_loads_speech_to_text_module() -> None:
    import leagent.tools.integration.speech_to_text as st_mod

    reg = ToolRegistry()
    count = reg.load_from_module(st_mod)
    assert count >= 1
    assert reg.has("speech_to_text")
