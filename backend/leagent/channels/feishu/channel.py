"""Feishu/Lark channel implementation for LeAgent.

Provides Feishu webhook integration with interactive card support
for enterprise messaging.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import base64
import os
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from ..base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from ..renderer import MessageRenderer, RenderStyle, normalize_feishu_markdown

logger = structlog.get_logger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
FEISHU_TOKEN_TTL_SECONDS = 7200


class FeishuChannel(BaseChannel):
    """Feishu/Lark channel for bot and webhook messaging.

    Supports webhook messaging and interactive card messages
    with rich formatting options.
    """

    channel_type = ChannelType.FEISHU
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        app_id: str = "",
        app_secret: str = "",
        webhook_url: str = "",
        webhook_secret: str = "",
        bot_prefix: str = "",
        process_handler: Any | None = None,
    ) -> None:
        """Initialize Feishu channel.

        Args:
            enabled: Whether channel is active.
            app_id: Feishu app ID.
            app_secret: Feishu app secret.
            webhook_url: Webhook URL for outgoing messages.
            webhook_secret: Webhook signature secret.
            bot_prefix: Prefix for bot messages.
            process_handler: Message processing handler.
        """
        super().__init__(
            enabled=enabled,
            bot_prefix=bot_prefix,
            process_handler=process_handler,
        )
        self.app_id = app_id
        self.app_secret = app_secret
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret

        self._token_value: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._http_session: Any = None

        self._receive_id_store: dict[str, str] = {}
        self._store_lock = asyncio.Lock()

        self._renderer = MessageRenderer(
            RenderStyle(
                supports_markdown=True,
                supports_code_fence=True,
                use_emoji=True,
            )
        )

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: Any | None = None,
    ) -> FeishuChannel:
        """Create Feishu channel from configuration.

        Args:
            config: Configuration dictionary.
            process_handler: Message processing handler.

        Returns:
            FeishuChannel instance.
        """
        return cls(
            enabled=config.get("enabled", True),
            app_id=config.get("app_id", ""),
            app_secret=config.get("app_secret", ""),
            webhook_url=config.get("webhook_url", ""),
            webhook_secret=config.get("webhook_secret", ""),
            bot_prefix=config.get("bot_prefix", ""),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> FeishuChannel:
        """Create Feishu channel from environment variables.

        Args:
            process_handler: Message processing handler.

        Returns:
            FeishuChannel instance.
        """
        return cls(
            enabled=os.getenv("FEISHU_CHANNEL_ENABLED", "1") == "1",
            app_id=os.getenv("FEISHU_APP_ID", ""),
            app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            webhook_url=os.getenv("FEISHU_WEBHOOK_URL", ""),
            webhook_secret=os.getenv("FEISHU_WEBHOOK_SECRET", ""),
            bot_prefix=os.getenv("FEISHU_BOT_PREFIX", ""),
            process_handler=process_handler,
        )

    async def _get_http_session(self) -> Any:
        """Get or create HTTP session."""
        if self._http_session is None:
            try:
                import aiohttp

                self._http_session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed for Feishu channel")
                raise
        return self._http_session

    async def _get_tenant_access_token(self) -> str:
        """Get and cache Feishu tenant access token.

        Returns:
            Access token string.
        """
        if not self.app_id or not self.app_secret:
            raise RuntimeError("Feishu app_id and app_secret required")

        now = time.time()
        if self._token_value and now < self._token_expires_at:
            return self._token_value

        async with self._token_lock:
            now = time.time()
            if self._token_value and now < self._token_expires_at:
                return self._token_value

            http = await self._get_http_session()
            url = f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal"
            payload = {
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            }

            async with http.post(url, json=payload) as resp:
                data = await resp.json()
                if data.get("code") != 0:
                    raise RuntimeError(f"Failed to get Feishu token: {data}")

            token = data.get("tenant_access_token")
            expires_in = data.get("expire", FEISHU_TOKEN_TTL_SECONDS)

            self._token_value = token
            self._token_expires_at = now + expires_in - 60
            return token

    def _generate_signature(self, timestamp: str) -> str:
        """Generate webhook signature.

        Args:
            timestamp: Current timestamp in seconds.

        Returns:
            Base64 encoded signature.
        """
        string_to_sign = f"{timestamp}\n{self.webhook_secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    async def _send_webhook(self, data: dict[str, Any]) -> bool:
        """Send message via webhook.

        Args:
            data: Message payload.

        Returns:
            True if sent successfully.
        """
        if not self.webhook_url:
            logger.warning("No webhook URL configured for Feishu")
            return False

        http = await self._get_http_session()

        payload = dict(data)
        if self.webhook_secret:
            timestamp = str(int(time.time()))
            payload["timestamp"] = timestamp
            payload["sign"] = self._generate_signature(timestamp)

        try:
            async with http.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                result = await resp.json()

                if resp.status >= 400 or result.get("code") != 0:
                    logger.error(
                        "Feishu webhook failed",
                        status=resp.status,
                        response=result,
                    )
                    return False

                return True

        except Exception as e:
            logger.exception("Feishu webhook error", error=str(e))
            return False

    async def _send_message_api(
        self,
        receive_id: str,
        msg_type: str,
        content: dict[str, Any],
        receive_id_type: str = "chat_id",
    ) -> bool:
        """Send message via Feishu API.

        Args:
            receive_id: Recipient ID.
            msg_type: Message type.
            content: Message content.
            receive_id_type: Type of receive_id.

        Returns:
            True if sent successfully.
        """
        try:
            token = await self._get_tenant_access_token()
        except Exception:
            logger.exception("Failed to get Feishu token")
            return False

        http = await self._get_http_session()
        url = f"{FEISHU_API_BASE}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        import json

        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content),
        }

        try:
            async with http.post(
                url,
                params=params,
                json=payload,
                headers=headers,
            ) as resp:
                result = await resp.json()

                if resp.status >= 400 or result.get("code") != 0:
                    logger.error(
                        "Feishu API send failed",
                        status=resp.status,
                        response=result,
                    )
                    return False

                return True

        except Exception as e:
            logger.exception("Feishu API error", error=str(e))
            return False

    def _format_text_message(self, text: str) -> dict[str, Any]:
        """Format a text message payload.

        Args:
            text: Message text.

        Returns:
            Feishu message content.
        """
        return {"text": text}

    def _format_interactive_card(
        self,
        title: str,
        content: str,
        *,
        buttons: list[dict[str, Any]] | None = None,
        color: str = "blue",
    ) -> dict[str, Any]:
        """Format an interactive card message.

        Args:
            title: Card title.
            content: Card content markdown.
            buttons: Optional action buttons.
            color: Card header color.

        Returns:
            Feishu card payload.
        """
        elements = [
            {
                "tag": "markdown",
                "content": normalize_feishu_markdown(content),
            }
        ]

        if buttons:
            actions = []
            for btn in buttons:
                actions.append(
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": btn.get("title", "")},
                        "type": btn.get("type", "primary"),
                        "url": btn.get("url", ""),
                    }
                )
            elements.append({"tag": "action", "actions": actions})

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        }

    async def _store_receive_id(self, session_id: str, receive_id: str) -> None:
        """Store receive_id for session.

        Args:
            session_id: Session identifier.
            receive_id: Feishu receive_id.
        """
        async with self._store_lock:
            self._receive_id_store[session_id] = receive_id

    async def _get_receive_id(self, session_id: str) -> str | None:
        """Get stored receive_id for session.

        Args:
            session_id: Session identifier.

        Returns:
            receive_id or None.
        """
        async with self._store_lock:
            return self._receive_id_store.get(session_id)

    async def consume_one(self, payload: Any) -> None:
        """Process one message from the queue.

        Args:
            payload: Message payload to process.
        """
        if not self.enabled:
            return

        if isinstance(payload, ChannelMessage):
            await self._process_channel_message(payload)
        elif isinstance(payload, dict):
            await self._process_dict_payload(payload)

    async def _process_channel_message(self, message: ChannelMessage) -> None:
        """Process a ChannelMessage.

        Args:
            message: Message to process.
        """
        receive_id = message.metadata.get("receive_id")
        if receive_id:
            await self._store_receive_id(message.session_id, receive_id)

        if self._process_handler:
            try:
                response_text = ""
                async for event in self._process_handler(message):
                    if isinstance(event, ChannelEvent):
                        content = event.data.get("content", "")
                        if content:
                            response_text += str(content) + "\n"

                if response_text:
                    await self.send(
                        message.sender_id,
                        response_text.strip(),
                        {
                            "session_id": message.session_id,
                            "receive_id": receive_id,
                        },
                    )

            except Exception:
                logger.exception("Error processing Feishu message")

    async def _process_dict_payload(self, payload: dict[str, Any]) -> None:
        """Process a dictionary payload."""
        receive_id = payload.get("receive_id")
        session_id = payload.get("session_id")
        if receive_id and session_id:
            await self._store_receive_id(session_id, receive_id)

        content = payload.get("content", "")
        if content:
            await self.send(
                payload.get("sender_id", ""),
                content,
                payload.get("metadata", {}),
            )

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send a text message.

        Args:
            to_handle: Recipient identifier.
            text: Message text.
            meta: Optional metadata.
        """
        if not self.enabled:
            return

        meta = meta or {}
        prefix = meta.get("bot_prefix", self.bot_prefix)
        full_text = f"{prefix}{text}" if prefix and text else text

        receive_id = meta.get("receive_id")
        if not receive_id:
            session_id = meta.get("session_id", to_handle)
            receive_id = await self._get_receive_id(session_id)

        if receive_id and self.app_id:
            content = self._format_text_message(full_text)
            await self._send_message_api(receive_id, "text", content)
        elif self.webhook_url:
            payload = {
                "msg_type": "text",
                "content": {"text": full_text},
            }
            await self._send_webhook(payload)

    async def send_event(
        self,
        *,
        user_id: str,
        session_id: str,
        event: ChannelEvent,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send an event.

        Args:
            user_id: Target user ID.
            session_id: Target session ID.
            event: Event to send.
            meta: Optional metadata.
        """
        if not self.enabled:
            return

        content = event.data.get("content", "")
        if content:
            merged_meta = dict(meta or {})
            merged_meta["session_id"] = session_id
            await self.send(user_id, str(content), merged_meta)

    async def send_interactive_card(
        self,
        to_handle: str,
        title: str,
        content: str,
        *,
        buttons: list[dict[str, Any]] | None = None,
        color: str = "blue",
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Send an interactive card message.

        Args:
            to_handle: Recipient identifier.
            title: Card title.
            content: Card content.
            buttons: Action buttons.
            color: Card header color.
            meta: Optional metadata.

        Returns:
            True if sent successfully.
        """
        if not self.enabled:
            return False

        card = self._format_interactive_card(title, content, buttons=buttons, color=color)

        meta = meta or {}
        receive_id = meta.get("receive_id")
        if not receive_id:
            session_id = meta.get("session_id", to_handle)
            receive_id = await self._get_receive_id(session_id)

        if receive_id and self.app_id:
            return await self._send_message_api(receive_id, "interactive", card)
        elif self.webhook_url:
            payload = {"msg_type": "interactive", "card": card}
            return await self._send_webhook(payload)

        return False

    async def start(self) -> None:
        """Start the Feishu channel."""
        if not self.enabled:
            logger.debug("Feishu channel disabled")
            return

        self._running = True

        if self.app_id and self.app_secret:
            try:
                await self._get_tenant_access_token()
                logger.info("Feishu access token obtained")
            except Exception:
                logger.exception("Failed to get Feishu access token")

        logger.info("Feishu channel started")

    async def stop(self) -> None:
        """Stop the Feishu channel."""
        if not self.enabled:
            return

        self._running = False

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        logger.info("Feishu channel stopped")

    async def health_check(self) -> dict[str, Any]:
        """Check channel health."""
        has_credentials = bool(self.app_id and self.app_secret)
        has_webhook = bool(self.webhook_url)

        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled and (has_credentials or has_webhook),
            "has_credentials": has_credentials,
            "has_webhook": has_webhook,
        }
