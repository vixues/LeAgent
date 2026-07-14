"""Tests for Weixin channel consume_one + agent bridge wiring (mocked)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest

from leagent.channels.agent_bridge import channel_session_id
from leagent.channels.base import ChannelEvent, ChannelMessage, ChannelType, MessageType
from leagent.channels.weixin.channel import WeixinChannel


async def _noop(*_a: Any, **_k: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_consume_one_with_fake_handler() -> None:
    sent: list[tuple[str, str]] = []

    async def fake_handler(message: ChannelMessage) -> AsyncIterator[ChannelEvent]:
        yield ChannelEvent(
            event_type="message",
            channel_type=ChannelType.WEIXIN,
            data={"content": f"echo:{message.content}"},
        )

    ch = WeixinChannel(
        enabled=True,
        account_id="acc",
        token="tok",
        process_handler=fake_handler,
    )

    async def fake_send(to_handle: str, text: str, meta: dict[str, Any] | None = None) -> None:
        sent.append((to_handle, text))

    ch.send = fake_send  # type: ignore[method-assign]
    ch._client = object()  # type: ignore[assignment]
    ch._start_typing = _noop  # type: ignore[method-assign]
    ch._stop_typing = _noop  # type: ignore[method-assign]
    ch._typing_keepalive = _noop  # type: ignore[method-assign]

    msg = ChannelMessage(
        channel_type=ChannelType.WEIXIN,
        message_type=MessageType.TEXT,
        content="hello",
        sender_id="user1",
        session_id="weixin:user1",
        metadata={},
    )
    await ch.consume_one(msg)
    assert sent == [("user1", "echo:hello")]


@pytest.mark.asyncio
async def test_consume_one_sends_produced_files(tmp_path: Any) -> None:
    sent_text: list[str] = []
    sent_arts: list[dict[str, Any]] = []
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    async def fake_handler(message: ChannelMessage) -> AsyncIterator[ChannelEvent]:
        yield ChannelEvent(
            event_type="message",
            channel_type=ChannelType.WEIXIN,
            data={
                "content": "已生成",
                "artifacts": [{"path": str(pdf), "filename": "report.pdf"}],
            },
        )

    ch = WeixinChannel(
        enabled=True,
        account_id="acc",
        token="tok",
        process_handler=fake_handler,
    )

    async def fake_send(to_handle: str, text: str, meta: dict[str, Any] | None = None) -> None:
        sent_text.append(text)

    async def fake_send_artifact(
        to_handle: str,
        artifact: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        sent_arts.append(artifact)
        return artifact.get("file_id")  # type: ignore[return-value]

    ch.send = fake_send  # type: ignore[method-assign]
    ch.send_artifact = fake_send_artifact  # type: ignore[method-assign]
    ch._client = object()  # type: ignore[assignment]
    ch._start_typing = _noop  # type: ignore[method-assign]
    ch._stop_typing = _noop  # type: ignore[method-assign]
    ch._typing_keepalive = _noop  # type: ignore[method-assign]

    msg = ChannelMessage(
        channel_type=ChannelType.WEIXIN,
        message_type=MessageType.TEXT,
        content="请生成 PDF",
        sender_id="user1",
        session_id="weixin:user1",
        metadata={},
    )
    await ch.consume_one(msg)
    assert sent_text == ["已生成"]
    assert len(sent_arts) == 1
    assert sent_arts[0]["filename"] == "report.pdf"


@pytest.mark.asyncio
async def test_consume_one_sends_image_artifact_and_strips_link() -> None:
    sent_text: list[str] = []
    sent_arts: list[dict[str, Any]] = []
    fid = "11111111-1111-1111-1111-111111111111"

    async def fake_handler(message: ChannelMessage) -> AsyncIterator[ChannelEvent]:
        yield ChannelEvent(
            event_type="message",
            channel_type=ChannelType.WEIXIN,
            data={
                "content": f"好了 ![图](/api/v1/files/{fid}/preview)",
                "artifacts": [
                    {
                        "file_id": fid,
                        "filename": "cat.png",
                        "content_type": "image/png",
                        "kind": "image",
                    }
                ],
            },
        )

    ch = WeixinChannel(
        enabled=True,
        account_id="acc",
        token="tok",
        process_handler=fake_handler,
    )

    async def fake_send(to_handle: str, text: str, meta: dict[str, Any] | None = None) -> None:
        sent_text.append(text)

    async def fake_send_artifact(
        to_handle: str,
        artifact: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        sent_arts.append(artifact)
        return str(artifact.get("file_id") or "")

    ch.send = fake_send  # type: ignore[method-assign]
    ch.send_artifact = fake_send_artifact  # type: ignore[method-assign]
    ch._client = object()  # type: ignore[assignment]
    ch._start_typing = _noop  # type: ignore[method-assign]
    ch._stop_typing = _noop  # type: ignore[method-assign]
    ch._typing_keepalive = _noop  # type: ignore[method-assign]

    msg = ChannelMessage(
        channel_type=ChannelType.WEIXIN,
        message_type=MessageType.TEXT,
        content="画只猫",
        sender_id="user1",
        session_id="weixin:user1",
        metadata={},
    )
    await ch.consume_one(msg)
    assert sent_arts[0]["file_id"] == fid
    assert sent_text == ["好了"]


def test_harvest_and_dedupe_file_id_path() -> None:
    from leagent.channels.outbound_artifacts import (
        dedupe_artifacts,
        harvest_artifacts_from_payload,
        strip_delivered_file_links,
    )

    fid = "22222222-2222-2222-2222-222222222222"
    arts = harvest_artifacts_from_payload(
        {
            "success": True,
            "file_id": fid,
            "preview_path": f"/api/v1/files/{fid}/preview",
            "filename": "img.png",
            "mime": "image/png",
            "storage_path": f"/tmp/{fid}_img.png",
        }
    )
    # Same file once via attachments and once via path-only should collapse.
    merged = dedupe_artifacts(
        [
            *arts,
            {"path": f"/tmp/{fid}_img.png"},
            {"file_id": fid, "filename": "file.bin"},
        ]
    )
    assert len(merged) == 1
    assert merged[0]["file_id"] == fid
    assert merged[0]["filename"] == "img.png"
    assert merged[0]["kind"] == "image"

    # tool_result frame: only dig into envelope (no phantom file.bin from outer ids)
    frame_arts = harvest_artifacts_from_payload(
        {
            "tool_use_id": "call_1",
            "name": "web_image_download",
            "success": True,
            "content": '{"file_id":"%s"}' % fid,
            "envelope": {
                "data": {
                    "file_id": fid,
                    "filename": "kitten.png",
                    "content_type": "image/png",
                    "preview_path": f"/api/v1/files/{fid}/preview",
                }
            },
        }
    )
    assert len(dedupe_artifacts(frame_arts)) == 1
    assert frame_arts[0]["filename"] == "kitten.png"

    cleaned = strip_delivered_file_links(
        f"完成\n![x](/api/v1/files/{fid}/preview)\n也见 /api/v1/files/{fid}/download",
        strip_all_file_api_links=True,
    )
    assert "preview" not in cleaned
    assert "download" not in cleaned
    assert "完成" in cleaned


def test_base64_aes_key_is_hex_wrapped() -> None:
    import base64

    from leagent.channels.weixin.media import base64_aes_key, build_file_item

    key = bytes(range(16))
    encoded = base64_aes_key(key)
    assert base64.b64decode(encoded).decode("ascii") == key.hex()
    item = build_file_item(
        {
            "media": {"encrypt_query_param": "p", "aes_key": encoded},
            "rawsize": 12,
            "ciphertext_size": 16,
        },
        "a.pdf",
    )
    assert item["file_item"]["file_name"] == "a.pdf"
    assert item["file_item"]["len"] == "12"
    assert item["file_item"]["media"]["encrypt_type"] == 1


def test_channel_session_id_stable() -> None:
    a = channel_session_id("weixin", "peer-1")
    b = channel_session_id("weixin", "peer-1")
    c = channel_session_id("weixin", "peer-2")
    assert isinstance(a, UUID)
    assert a == b
    assert a != c


@pytest.mark.asyncio
async def test_agent_bridge_yields_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.channels import agent_bridge
    from leagent.sdk.events import AgentEvent, AgentEventType
    from leagent.services.auth.service import LOCAL_USER_ID

    captured: dict[str, Any] = {}

    class FakeRuntime:
        @classmethod
        def from_service_manager(cls, _sm: Any) -> FakeRuntime:
            return cls()

        async def stream(self, *_a: Any, **kwargs: Any) -> AsyncIterator[AgentEvent]:
            captured.update(kwargs)
            yield AgentEvent(type=AgentEventType.ASSISTANT, data={"content": "ok"})
            yield AgentEvent(type=AgentEventType.RESULT, data={"reason": "completed"})

    monkeypatch.setattr(agent_bridge, "AgentRuntime", FakeRuntime, raising=False)

    # process_channel_message imports AgentRuntime from leagent.sdk inside the body
    import leagent.sdk as sdk_mod

    monkeypatch.setattr(sdk_mod, "AgentRuntime", FakeRuntime)

    class FakeSM:
        session_manager = None

    msg = ChannelMessage(
        channel_type=ChannelType.WEIXIN,
        content="hi",
        sender_id="u1",
        session_id="weixin:u1",
    )
    events = [
        e
        async for e in agent_bridge.process_channel_message(FakeSM(), msg)  # type: ignore[arg-type]
    ]
    assert len(events) == 1
    assert events[0].data["content"] == "ok"
    assert captured.get("user_id") == LOCAL_USER_ID
    assert "instant-messaging" in str(captured.get("append_system_prompt") or "")
