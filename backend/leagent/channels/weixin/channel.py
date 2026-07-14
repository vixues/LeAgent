"""Weixin (personal WeChat) channel via Tencent iLink Bot API."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Any

import structlog

from ..base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from .client import (
    ILINK_BASE_URL,
    TYPING_START,
    TYPING_STOP,
    WEIXIN_CDN_BASE_URL,
    SessionExpiredError,
    WeixinClient,
)
from .media import (
    build_file_item,
    build_image_item,
    extract_inbound_media,
    media_type_for_kind,
    upload_encrypted_media,
)
from .store import (
    ContextTokenStore,
    MessageDeduplicator,
    TypingTicketCache,
    load_account,
    load_sync_buf,
    save_sync_buf,
)

logger = structlog.get_logger(__name__)

MAX_MESSAGE_LENGTH = 4000
MESSAGE_DEDUP_TTL_SECONDS = 300
MAX_CONSECUTIVE_FAILURES = 3
RETRY_DELAY_SECONDS = 2
BACKOFF_DELAY_SECONDS = 30
CHUNK_SEND_DELAY_SECONDS = 0.15

_FENCE_RE = re.compile(r"^```([^\n`]*)\s*$")


def check_weixin_requirements() -> bool:
    """Return True when aiohttp and cryptography are importable."""
    try:
        import aiohttp  # noqa: F401
        from cryptography.hazmat.primitives.ciphers import Cipher  # noqa: F401

        return True
    except ImportError:
        return False


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _split_markdown_blocks(content: str) -> list[str]:
    if not content:
        return []
    blocks: list[str] = []
    lines = content.splitlines()
    current: list[str] = []
    in_code_block = False

    for raw_line in lines:
        line = raw_line.rstrip()
        if _FENCE_RE.match(line.strip()):
            if not in_code_block and current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line)
            in_code_block = not in_code_block
            if not in_code_block:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if in_code_block:
            current.append(line)
            continue
        if not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _hard_truncate(text: str, max_length: int) -> list[str]:
    if len(text) <= max_length:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        parts.append(text[start : start + max_length])
        start += max_length
    return parts


def split_text_for_delivery(
    content: str,
    max_length: int = MAX_MESSAGE_LENGTH,
    *,
    split_per_line: bool = False,
) -> list[str]:
    """Split outbound text for Weixin delivery.

    Default keeps a single bubble when under *max_length*; only pack by
    markdown blocks when the payload exceeds the limit.
    """
    text = (content or "").strip()
    if not text:
        return []

    if split_per_line:
        units: list[str] = []
        for block in _split_markdown_blocks(text):
            if _FENCE_RE.match(block.splitlines()[0].strip()):
                units.extend(_hard_truncate(block, max_length))
                continue
            for line in block.splitlines():
                if line.strip():
                    units.extend(_hard_truncate(line.strip(), max_length))
        return units

    if len(text) <= max_length:
        return [text]

    packed: list[str] = []
    current = ""
    for block in _split_markdown_blocks(text):
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            packed.append(current)
            current = ""
        if len(block) <= max_length:
            current = block
        else:
            packed.extend(_hard_truncate(block, max_length))
    if current:
        packed.append(current)
    return packed


def guess_chat_type(message: dict[str, Any], _account_id: str = "") -> tuple[str, str]:
    """Return ``(chat_type, chat_id)`` — chat_type is ``dm`` or ``group``."""
    room_id = str(message.get("room_id") or message.get("chat_room_id") or "").strip()
    if room_id:
        return "group", room_id
    return "dm", str(message.get("from_user_id") or "")


class WeixinChannel(BaseChannel):
    """Personal WeChat channel using iLink Bot long-polling."""

    channel_type = ChannelType.WEIXIN
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        account_id: str = "",
        token: str = "",
        base_url: str = ILINK_BASE_URL,
        cdn_base_url: str = WEIXIN_CDN_BASE_URL,
        dm_policy: str = "open",
        group_policy: str = "disabled",
        allow_from: list[str] | None = None,
        group_allow_from: list[str] | None = None,
        split_multiline_messages: bool = False,
        bot_prefix: str = "",
        process_handler: Any | None = None,
    ) -> None:
        super().__init__(
            enabled=enabled,
            bot_prefix=bot_prefix,
            process_handler=process_handler,
        )
        self.account_id = account_id.strip()
        self.token = token.strip()
        self.base_url = (base_url or ILINK_BASE_URL).rstrip("/")
        self.cdn_base_url = (cdn_base_url or WEIXIN_CDN_BASE_URL).rstrip("/")
        self.dm_policy = (dm_policy or "open").strip().lower()
        self.group_policy = (group_policy or "disabled").strip().lower()
        self.allow_from = list(allow_from or [])
        self.group_allow_from = list(group_allow_from or [])
        self.split_multiline_messages = split_multiline_messages

        if self.account_id and not self.token:
            persisted = load_account(self.account_id)
            if persisted:
                self.token = str(persisted.get("token") or "").strip()
                self.base_url = str(persisted.get("base_url") or self.base_url).rstrip("/")

        self._client: WeixinClient | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._token_store = ContextTokenStore()
        self._typing_cache = TypingTicketCache()
        self._dedup = MessageDeduplicator(ttl_seconds=MESSAGE_DEDUP_TTL_SECONDS)
        self._send_lock = asyncio.Lock()
        self._session_expired = False

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: Any | None = None,
    ) -> WeixinChannel:
        extra = dict(config.get("extra") or {})
        return cls(
            enabled=config.get("enabled", True),
            account_id=str(extra.get("account_id") or config.get("account_id") or ""),
            token=str(config.get("token") or extra.get("token") or ""),
            base_url=str(extra.get("base_url") or ILINK_BASE_URL),
            cdn_base_url=str(extra.get("cdn_base_url") or WEIXIN_CDN_BASE_URL),
            dm_policy=str(extra.get("dm_policy") or "open"),
            group_policy=str(extra.get("group_policy") or "disabled"),
            allow_from=_coerce_list(extra.get("allow_from")),
            group_allow_from=_coerce_list(extra.get("group_allow_from")),
            split_multiline_messages=_coerce_bool(extra.get("split_multiline_messages")),
            bot_prefix=str(config.get("bot_prefix") or extra.get("bot_prefix") or ""),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> WeixinChannel:
        return cls(
            enabled=os.getenv("WEIXIN_CHANNEL_ENABLED", "1") == "1",
            account_id=os.getenv("WEIXIN_ACCOUNT_ID", ""),
            token=os.getenv("WEIXIN_TOKEN", ""),
            base_url=os.getenv("WEIXIN_BASE_URL", ILINK_BASE_URL),
            cdn_base_url=os.getenv("WEIXIN_CDN_BASE_URL", WEIXIN_CDN_BASE_URL),
            dm_policy=os.getenv("WEIXIN_DM_POLICY", "open"),
            group_policy=os.getenv("WEIXIN_GROUP_POLICY", "disabled"),
            allow_from=_coerce_list(os.getenv("WEIXIN_ALLOWED_USERS", "")),
            group_allow_from=_coerce_list(os.getenv("WEIXIN_GROUP_ALLOWED_USERS", "")),
            split_multiline_messages=_coerce_bool(
                os.getenv("WEIXIN_SPLIT_MULTILINE_MESSAGES")
            ),
            bot_prefix=os.getenv("WEIXIN_BOT_PREFIX", ""),
            process_handler=process_handler,
        )

    def _allowed(self, chat_type: str, peer_id: str) -> bool:
        if chat_type == "group":
            if self.group_policy == "disabled":
                return False
            if self.group_policy == "allowlist":
                return peer_id in self.group_allow_from
            return self.group_policy == "open"
        # DM
        if self.dm_policy == "disabled":
            return False
        if self.dm_policy == "allowlist":
            return peer_id in self.allow_from
        return self.dm_policy in {"open", "pairing"}

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Weixin channel disabled, skip start")
            return
        if not check_weixin_requirements():
            raise RuntimeError("Weixin startup failed: aiohttp and cryptography are required")
        if not self.token:
            raise RuntimeError("Weixin startup failed: WEIXIN_TOKEN is required")
        if not self.account_id:
            raise RuntimeError("Weixin startup failed: WEIXIN_ACCOUNT_ID is required")

        restored = self._token_store.restore(self.account_id)
        if restored:
            logger.info("weixin restored context tokens", count=restored)

        if self.group_policy != "disabled":
            logger.warning(
                "WEIXIN_GROUP_POLICY=%s is set, but QR-login connects an iLink bot "
                "identity which typically cannot receive ordinary WeChat group events. "
                "If group messages never arrive, the limitation is on the iLink side.",
                self.group_policy,
            )

        self._client = WeixinClient(
            token=self.token,
            base_url=self.base_url,
            cdn_base_url=self.cdn_base_url,
        )
        self._running = True
        self._session_expired = False
        self._poll_task = asyncio.create_task(self._poll_loop(), name="weixin-poll")
        logger.info(
            "Weixin channel started",
            account_id=self.account_id[:12],
            base_url=self.base_url,
        )

    async def stop(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        if self._client:
            await self._client.close()
            self._client = None
        logger.info("Weixin channel stopped")

    async def _poll_loop(self) -> None:
        assert self._client is not None
        sync_buf = load_sync_buf(self.account_id)
        consecutive_failures = 0

        while self._running:
            if self._session_expired:
                logger.error("weixin session expired; stop polling until re-login")
                await asyncio.sleep(600)
                continue
            try:
                response = await self._client.get_updates(sync_buf)
                consecutive_failures = 0
                new_buf = str(response.get("get_updates_buf") or sync_buf)
                if new_buf != sync_buf:
                    sync_buf = new_buf
                    save_sync_buf(self.account_id, sync_buf)

                msgs = response.get("msgs") or response.get("msg_list") or []
                if isinstance(msgs, dict):
                    msgs = [msgs]
                for raw in msgs:
                    if isinstance(raw, dict):
                        await self._dispatch_inbound(raw)
            except SessionExpiredError:
                self._session_expired = True
                self._token_store.clear_account(self.account_id)
                logger.error("weixin session expired (errcode=-14); re-run channels login weixin")
            except asyncio.CancelledError:
                break
            except Exception:
                consecutive_failures += 1
                delay = (
                    BACKOFF_DELAY_SECONDS
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES
                    else RETRY_DELAY_SECONDS
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                logger.exception("weixin poll error", delay=delay)
                await asyncio.sleep(delay)

    async def _dispatch_inbound(self, raw: dict[str, Any]) -> None:
        msg_id = str(
            raw.get("msg_id")
            or raw.get("message_id")
            or raw.get("client_id")
            or ""
        )
        if msg_id and self._dedup.seen(msg_id):
            return

        # Ignore bot's own messages
        if int(raw.get("message_type") or 0) == 2:
            return

        from_user = str(raw.get("from_user_id") or "").strip()
        if not from_user:
            return

        chat_type, chat_id = guess_chat_type(raw, self.account_id)
        peer_for_policy = chat_id if chat_type == "group" else from_user
        if not self._allowed(chat_type, peer_for_policy):
            logger.debug(
                "weixin message filtered by policy",
                chat_type=chat_type,
                peer=peer_for_policy[:16],
            )
            return

        context_token = str(raw.get("context_token") or "").strip()
        if context_token:
            self._token_store.set(self.account_id, from_user, context_token)

        text_parts: list[str] = []
        media_meta: list[dict[str, Any]] = []
        for item in raw.get("item_list") or []:
            if not isinstance(item, dict):
                continue
            item_type = int(item.get("type") or 0)
            if item_type == 1:  # text
                text = (item.get("text_item") or {}).get("text") or item.get("text") or ""
                if text:
                    text_parts.append(str(text))
            elif self._client:
                extracted = await extract_inbound_media(self._client, item)
                if extracted:
                    kind, data, filename = extracted
                    if kind == "voice_text":
                        text_parts.append(data.decode("utf-8", errors="replace"))
                    else:
                        media_meta.append(
                            {
                                "kind": kind,
                                "filename": filename,
                                "size": len(data),
                                "bytes": data,
                            }
                        )
                        text_parts.append(f"[{kind}: {filename}]")

        content = "\n".join(text_parts).strip()
        if not content and not media_meta:
            return

        session_id = self.resolve_session_id(from_user, {"chat_type": chat_type})
        message = ChannelMessage(
            channel_type=ChannelType.WEIXIN,
            message_type=MessageType.TEXT,
            content=content or "[media]",
            sender_id=from_user,
            recipient_id=self.account_id,
            session_id=session_id,
            metadata={
                "context_token": context_token,
                "chat_type": chat_type,
                "chat_id": chat_id,
                "msg_id": msg_id,
                "media": [
                    {k: v for k, v in m.items() if k != "bytes"} for m in media_meta
                ],
                "media_bytes": media_meta,
            },
        )

        if self._enqueue:
            self._enqueue(message)
        else:
            await self.consume_one(message)

    async def consume_one(self, payload: Any) -> None:
        if not self.enabled:
            return
        if isinstance(payload, ChannelMessage):
            await self._process_channel_message(payload)
        elif isinstance(payload, dict):
            msg = ChannelMessage.from_dict(payload)
            await self._process_channel_message(msg)

    async def _process_channel_message(self, message: ChannelMessage) -> None:
        peer = message.sender_id
        typing_task: asyncio.Task[None] | None = None
        try:
            # Typing (getconfig + keepalive) must not block the agent turn —
            # getconfig alone can cost hundreds of ms on a cold ticket cache.
            context_token = message.metadata.get("context_token")
            typing_task = asyncio.create_task(
                self._typing_while_busy(peer, context_token),
                name=f"weixin-typing-{peer[:16]}",
            )

            response_text = ""
            artifacts: list[dict[str, Any]] = []
            if self._process_handler:
                async for event in self._process_handler(message):
                    if isinstance(event, ChannelEvent):
                        content = event.data.get("content", "")
                        if content:
                            response_text += str(content)
                        for art in event.data.get("artifacts") or []:
                            if isinstance(art, dict):
                                artifacts.append(art)
                    elif isinstance(event, dict):
                        content = event.get("content") or (event.get("data") or {}).get(
                            "content", ""
                        )
                        if content:
                            response_text += str(content)
                        data = event.get("data") if isinstance(event.get("data"), dict) else event
                        for art in (data or {}).get("artifacts") or []:
                            if isinstance(art, dict):
                                artifacts.append(art)

            meta = {
                "session_id": message.session_id,
                "context_token": context_token,
            }

            from leagent.channels.outbound_artifacts import (
                dedupe_artifacts,
                strip_delivered_file_links,
            )

            outbound = dedupe_artifacts(artifacts)
            sent_ok = 0
            for art in outbound:
                try:
                    await self.send_artifact(peer, art, meta=meta)
                    sent_ok += 1
                except Exception:
                    logger.exception(
                        "weixin failed to send artifact",
                        artifact={k: art.get(k) for k in ("file_id", "path", "filename")},
                        peer=peer[:24],
                    )
                    try:
                        label = art.get("filename") or art.get("file_id") or "file"
                        await self.send(peer, f"文件已生成，但发送失败：{label}", meta)
                    except Exception:
                        logger.debug("weixin file-fail notice send failed", exc_info=True)

            # Strip any leftover File API links even if send partially failed.
            response_text = strip_delivered_file_links(
                response_text, strip_all_file_api_links=True
            )

            if response_text.strip():
                await self.send(peer, response_text.strip(), meta)
            elif sent_ok == 0 and not outbound:
                # Keep quiet if everything was empty after stripping.
                pass
        except Exception:
            logger.exception("Error processing Weixin message")
            try:
                await self.send(peer, "抱歉，处理消息时出现错误。", message.metadata)
            except Exception:
                logger.exception("Failed to send Weixin error reply")
        finally:
            if typing_task:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass
            await self._stop_typing(peer)

    async def _typing_while_busy(
        self,
        user_id: str,
        context_token: str | None = None,
    ) -> None:
        """Start typing then keep the indicator alive until cancelled."""
        await self._start_typing(user_id, context_token)
        await self._typing_keepalive(user_id)

    async def _ensure_typing_ticket(
        self,
        user_id: str,
        context_token: str | None = None,
    ) -> str | None:
        if not self._client:
            return None
        cached = self._typing_cache.get(user_id)
        if cached:
            return cached
        try:
            cfg = await self._client.get_config(
                user_id=user_id,
                context_token=context_token
                or self._token_store.get(self.account_id, user_id),
            )
            ticket = str(cfg.get("typing_ticket") or cfg.get("ticket") or "").strip()
            if ticket:
                self._typing_cache.set(user_id, ticket)
            return ticket or None
        except Exception:
            logger.debug("weixin getconfig failed", exc_info=True)
            return None

    async def _start_typing(self, user_id: str, context_token: str | None = None) -> None:
        if not self._client:
            return
        ticket = await self._ensure_typing_ticket(user_id, context_token)
        if not ticket:
            return
        try:
            await self._client.send_typing(
                to_user_id=user_id,
                typing_ticket=ticket,
                status=TYPING_START,
            )
        except Exception:
            logger.debug("weixin send_typing start failed", exc_info=True)

    async def _stop_typing(self, user_id: str) -> None:
        if not self._client:
            return
        ticket = self._typing_cache.get(user_id)
        if not ticket:
            return
        try:
            await self._client.send_typing(
                to_user_id=user_id,
                typing_ticket=ticket,
                status=TYPING_STOP,
            )
        except Exception:
            logger.debug("weixin send_typing stop failed", exc_info=True)

    async def _typing_keepalive(self, user_id: str) -> None:
        while True:
            await asyncio.sleep(5.0)
            await self._start_typing(user_id)

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not self._client:
            raise RuntimeError("Weixin channel is not started")

        peer = to_handle
        if ":" in to_handle and to_handle.startswith("weixin:"):
            peer = to_handle.split(":", 1)[1]

        meta = meta or {}
        context_token = (
            str(meta.get("context_token") or "").strip()
            or self._token_store.get(self.account_id, peer)
        )
        chunks = split_text_for_delivery(
            text,
            MAX_MESSAGE_LENGTH,
            split_per_line=self.split_multiline_messages,
        )
        async with self._send_lock:
            for i, chunk in enumerate(chunks):
                client_id = uuid.uuid4().hex
                try:
                    await self._client.send_text(
                        to=peer,
                        text=chunk,
                        context_token=context_token,
                        client_id=client_id,
                    )
                except SessionExpiredError:
                    self._session_expired = True
                    raise
                if i < len(chunks) - 1:
                    await asyncio.sleep(CHUNK_SEND_DELAY_SECONDS)

    async def send_image_bytes(
        self,
        to_handle: str,
        data: bytes,
        *,
        filename: str = "image.jpg",
        meta: dict[str, Any] | None = None,
    ) -> None:
        await self._send_media(to_handle, data, kind="image", filename=filename, meta=meta)

    async def send_file_bytes(
        self,
        to_handle: str,
        data: bytes,
        *,
        filename: str = "file.bin",
        meta: dict[str, Any] | None = None,
    ) -> None:
        await self._send_media(to_handle, data, kind="file", filename=filename, meta=meta)

    async def send_local_file(
        self,
        to_handle: str,
        path: str | os.PathLike[str],
        *,
        meta: dict[str, Any] | None = None,
        filename: str | None = None,
    ) -> None:
        """Read a local artifact and send it as an image or file attachment."""
        await self.send_artifact(
            to_handle,
            {"path": str(path), "filename": filename or Path(path).name},
            meta=meta,
        )

    async def send_artifact(
        self,
        to_handle: str,
        artifact: dict[str, Any],
        *,
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        """Send a managed or local artifact as native WeChat media.

        Returns the delivered ``file_id`` when known (for link stripping).
        """
        from leagent.channels.outbound_artifacts import (
            is_image_artifact,
            load_artifact_bytes,
        )

        data, filename, content_type = await load_artifact_bytes(artifact)
        kind = "image" if is_image_artifact(
            filename=filename,
            content_type=content_type,
            kind=str(artifact.get("kind") or ""),
        ) else "file"
        if kind == "image":
            await self.send_image_bytes(to_handle, data, filename=filename, meta=meta)
        else:
            await self.send_file_bytes(to_handle, data, filename=filename, meta=meta)
        fid = artifact.get("file_id")
        return str(fid) if fid else None

    async def _send_media(
        self,
        to_handle: str,
        data: bytes,
        *,
        kind: str,
        filename: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        if not self._client:
            raise RuntimeError("Weixin channel is not started")
        peer = to_handle.split(":", 1)[1] if to_handle.startswith("weixin:") else to_handle
        meta = meta or {}
        context_token = (
            str(meta.get("context_token") or "").strip()
            or self._token_store.get(self.account_id, peer)
        )
        upload = await upload_encrypted_media(
            self._client,
            to_user_id=peer,
            data=data,
            media_type=media_type_for_kind(kind),
            filename=filename,
        )
        if kind == "image":
            item = build_image_item(upload)
        else:
            item = build_file_item(upload, filename)

        async with self._send_lock:
            await self._client.send_media_message(
                to=peer,
                item=item,
                context_token=context_token,
                client_id=uuid.uuid4().hex,
            )

    async def send_event(
        self,
        *,
        user_id: str,
        session_id: str,
        event: ChannelEvent,
        meta: dict[str, Any] | None = None,
    ) -> None:
        content = event.data.get("content", "")
        if content:
            await self.send(user_id, str(content), {**(meta or {}), "session_id": session_id})

    async def health_check(self) -> dict[str, Any]:
        base = await super().health_check()
        base.update(
            {
                "account_id": self.account_id[:12] if self.account_id else "",
                "session_expired": self._session_expired,
                "has_token": bool(self.token),
            }
        )
        return base
