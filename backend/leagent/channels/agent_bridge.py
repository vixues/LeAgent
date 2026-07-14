"""Bridge inbound channel messages to ``AgentRuntime.stream``.

Yields :class:`~leagent.channels.base.ChannelEvent` frames with aggregated
assistant text (final reply only — no stream deltas to IM clients) plus any
tool-produced artifacts for native media delivery.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

import structlog

from leagent.channels.base import ChannelEvent, ChannelMessage, ChannelType
from leagent.channels.outbound_artifacts import (
    dedupe_artifacts,
    harvest_artifacts_from_payload,
    harvest_file_ids_from_text,
    strip_delivered_file_links,
)
from leagent.sdk.events import AgentEventType
from leagent.services.auth.service import LOCAL_USER_ID

if TYPE_CHECKING:
    from leagent.services.service_manager import ServiceManager

logger = structlog.get_logger(__name__)

# Stable namespace for deterministic per-peer session UUIDs.
_CHANNEL_SESSION_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Instant-messaging channels where verbose tool exploration hurts latency.
_IM_CHANNEL_TYPES = frozenset({"weixin", "dingtalk", "feishu", "wechat_work"})

_IM_SYSTEM_HINT = (
    "You are chatting over an instant-messaging channel (WeChat / mobile). "
    "Reply with concise plain text suitable for chat bubbles. "
    "For image requests prefer the built-in `image_generate` tool (or "
    "`web_image_download` after you have an HTTPS image URL). Do not explore "
    "the local filesystem unless the user explicitly asks. "
    "Generated images and files are delivered automatically as native WeChat "
    "attachments — never paste /api/v1/files preview links, markdown image "
    "embeds, localhost URLs, download URLs, or local disk paths in your reply."
)


def channel_session_id(channel: str, peer_id: str) -> UUID:
    """Deterministic UUID for a channel peer so multi-turn context sticks."""
    return uuid5(_CHANNEL_SESSION_NS, f"{channel}:{peer_id}")


def resolve_channel_owner_user_id(service_manager: Any) -> UUID:
    """Owner for channel-backed chat sessions (NOT NULL on ``chat_sessions``)."""
    for attr in ("default_user_id", "local_user_id", "owner_user_id"):
        raw = getattr(service_manager, attr, None)
        if raw is None:
            continue
        try:
            return raw if isinstance(raw, UUID) else UUID(str(raw))
        except (TypeError, ValueError):
            continue
    return LOCAL_USER_ID


def make_agent_process_handler(
    service_manager: ServiceManager,
    *,
    agent_name: str = "default_agent",
) -> Any:
    """Build a ``ProcessHandler`` bound to *service_manager*."""

    async def handler(message: ChannelMessage) -> AsyncIterator[ChannelEvent]:
        async for event in process_channel_message(
            service_manager,
            message,
            agent_name=agent_name,
        ):
            yield event

    return handler


async def process_channel_message(
    service_manager: ServiceManager,
    message: ChannelMessage,
    *,
    agent_name: str = "default_agent",
) -> AsyncIterator[ChannelEvent]:
    """Run one agent turn for an inbound channel message and yield reply events."""
    from leagent.sdk import AgentRuntime

    text = (message.content or "").strip()
    if not text:
        return

    channel = (
        message.channel_type.value
        if isinstance(message.channel_type, ChannelType)
        else str(message.channel_type)
    )
    peer = message.sender_id
    session_uuid = channel_session_id(channel, peer)
    owner_user_id = resolve_channel_owner_user_id(service_manager)
    im_hint = _IM_SYSTEM_HINT if channel in _IM_CHANNEL_TYPES else ""

    # Ensure session state exists for multi-turn continuity (must set user_id —
    # ``chat_sessions.user_id`` is NOT NULL).
    sm = getattr(service_manager, "session_manager", None)
    if sm is not None:
        try:
            await sm.get_or_create(session_uuid, user_id=owner_user_id)
        except Exception:
            logger.debug("channel session get_or_create failed", exc_info=True)

    runtime = AgentRuntime.from_service_manager(service_manager)
    final_text = ""
    text_parts: list[str] = []
    artifacts: list[dict[str, Any]] = []

    try:
        async for event in runtime.stream(
            agent_name,
            text,
            session_id=session_uuid,
            user_id=owner_user_id,
            append_system_prompt=im_hint,
            tool_extra={
                "platform": channel,
                "external_user_id": peer,
                "channel_session_id": message.session_id,
            },
        ):
            etype = event.type
            data = event.data or {}
            if etype == AgentEventType.STREAM_DELTA:
                delta = data.get("content")
                if delta:
                    text_parts.append(str(delta))
            elif etype == AgentEventType.ASSISTANT:
                final_text = str(data.get("content") or "")
            elif etype in (
                AgentEventType.WORKSPACE_ATTACHMENTS,
                AgentEventType.TOOL_RESULT,
            ):
                artifacts.extend(harvest_artifacts_from_payload(data))
            elif etype == AgentEventType.RESULT:
                if data.get("error"):
                    logger.warning(
                        "channel agent turn error",
                        channel=channel,
                        error=data.get("error"),
                    )
    except Exception:
        logger.exception("channel agent bridge failed", channel=channel, peer=peer[:24])
        yield ChannelEvent(
            event_type="message",
            channel_type=message.channel_type,
            data={"content": "抱歉，Agent 处理失败，请稍后重试。"},
        )
        return

    reply = (final_text or "".join(text_parts)).strip()

    # Salvage file ids the model pasted as preview links (also force-send them).
    for fid in harvest_file_ids_from_text(reply):
        artifacts.append({"file_id": fid, "filename": "image.png", "kind": "image"})

    unique = dedupe_artifacts(artifacts)
    # Always strip File API preview/download links from IM text.
    reply = strip_delivered_file_links(reply, strip_all_file_api_links=True)

    if reply or unique:
        yield ChannelEvent(
            event_type="message",
            channel_type=message.channel_type,
            data={
                "content": reply,
                "artifacts": unique,
                "session_id": str(session_uuid),
            },
        )
