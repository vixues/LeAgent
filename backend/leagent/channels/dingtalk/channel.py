"""DingTalk channel implementation for LeAgent.

Provides DingTalk webhook and bot integration with message
card formatting support.
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
from urllib.parse import quote_plus

import structlog

from ..base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from ..renderer import MessageRenderer, RenderStyle, normalize_dingtalk_markdown

logger = structlog.get_logger(__name__)

DINGTALK_TOKEN_TTL_SECONDS = 7200
DINGTALK_API_BASE = "https://api.dingtalk.com"
DINGTALK_OAPI_BASE = "https://oapi.dingtalk.com"


class DingTalkChannel(BaseChannel):
    """DingTalk channel for bot and webhook messaging.

    Supports both incoming webhooks and bot conversations
    with message card formatting.
    """

    channel_type = ChannelType.DINGTALK
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        client_id: str = "",
        client_secret: str = "",
        webhook_url: str = "",
        webhook_secret: str = "",
        bot_prefix: str = "[BOT] ",
        process_handler: Any | None = None,
    ) -> None:
        """Initialize DingTalk channel.

        Args:
            enabled: Whether channel is active.
            client_id: DingTalk app key.
            client_secret: DingTalk app secret.
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
        self.client_id = client_id
        self.client_secret = client_secret
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret

        self._token_value: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._http_session: Any = None

        self._session_webhooks: dict[str, str] = {}
        self._webhook_lock = asyncio.Lock()

        self._renderer = MessageRenderer(
            RenderStyle(
                supports_markdown=True,
                supports_code_fence=True,
                max_length=3500,
                use_emoji=True,
            )
        )

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: Any | None = None,
    ) -> DingTalkChannel:
        """Create DingTalk channel from configuration.

        Args:
            config: Configuration dictionary.
            process_handler: Message processing handler.

        Returns:
            DingTalkChannel instance.
        """
        return cls(
            enabled=config.get("enabled", True),
            client_id=config.get("client_id", ""),
            client_secret=config.get("client_secret", ""),
            webhook_url=config.get("webhook_url", ""),
            webhook_secret=config.get("webhook_secret", ""),
            bot_prefix=config.get("bot_prefix", "[BOT] "),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> DingTalkChannel:
        """Create DingTalk channel from environment variables.

        Args:
            process_handler: Message processing handler.

        Returns:
            DingTalkChannel instance.
        """
        return cls(
            enabled=os.getenv("DINGTALK_CHANNEL_ENABLED", "1") == "1",
            client_id=os.getenv("DINGTALK_CLIENT_ID", ""),
            client_secret=os.getenv("DINGTALK_CLIENT_SECRET", ""),
            webhook_url=os.getenv("DINGTALK_WEBHOOK_URL", ""),
            webhook_secret=os.getenv("DINGTALK_WEBHOOK_SECRET", ""),
            bot_prefix=os.getenv("DINGTALK_BOT_PREFIX", "[BOT] "),
            process_handler=process_handler,
        )

    async def _get_http_session(self) -> Any:
        """Get or create HTTP session.

        Returns:
            aiohttp ClientSession.
        """
        if self._http_session is None:
            try:
                import aiohttp

                self._http_session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed for DingTalk channel")
                raise

        return self._http_session

    async def _get_access_token(self) -> str:
        """Get and cache DingTalk access token.

        Returns:
            Access token string.

        Raises:
            RuntimeError: If credentials missing or token fetch fails.
        """
        if not self.client_id or not self.client_secret:
            raise RuntimeError("DingTalk client_id and client_secret required")

        now = time.time()
        if self._token_value and now < self._token_expires_at:
            return self._token_value

        async with self._token_lock:
            now = time.time()
            if self._token_value and now < self._token_expires_at:
                return self._token_value

            http = await self._get_http_session()
            url = f"{DINGTALK_API_BASE}/v1.0/oauth2/accessToken"
            payload = {
                "appKey": self.client_id,
                "appSecret": self.client_secret,
            }

            async with http.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status >= 400:
                    raise RuntimeError(f"Failed to get access token: {data}")

            token = data.get("accessToken") or data.get("access_token")
            if not token:
                raise RuntimeError(f"No access token in response: {data}")

            self._token_value = token
            self._token_expires_at = now + DINGTALK_TOKEN_TTL_SECONDS - 60
            return token

    def _generate_signature(self, timestamp: str) -> str:
        """Generate webhook signature.

        Args:
            timestamp: Current timestamp in milliseconds.

        Returns:
            Base64 encoded signature.
        """
        secret = self.webhook_secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.webhook_secret}"
        hmac_code = hmac.new(
            secret,
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return quote_plus(base64.b64encode(hmac_code).decode("utf-8"))

    async def _send_webhook(
        self,
        data: dict[str, Any],
        webhook_url: str | None = None,
    ) -> bool:
        """Send message via webhook.

        Args:
            data: Message payload.
            webhook_url: Override webhook URL.

        Returns:
            True if sent successfully.
        """
        url = webhook_url or self.webhook_url
        if not url:
            logger.warning("No webhook URL configured for DingTalk")
            return False

        if self.webhook_secret and not webhook_url:
            timestamp = str(int(time.time() * 1000))
            sign = self._generate_signature(timestamp)
            url = f"{url}&timestamp={timestamp}&sign={sign}"

        http = await self._get_http_session()

        try:
            async with http.post(
                url,
                json=data,
                headers={"Content-Type": "application/json"},
            ) as resp:
                result = await resp.json()

                if resp.status >= 400:
                    logger.error(
                        "DingTalk webhook failed",
                        status=resp.status,
                        response=result,
                    )
                    return False

                errcode = result.get("errcode", 0)
                if errcode != 0:
                    logger.error(
                        "DingTalk API error",
                        errcode=errcode,
                        errmsg=result.get("errmsg"),
                    )
                    return False

                return True

        except Exception as e:
            logger.exception("DingTalk webhook error", error=str(e))
            return False

    def _format_text_message(self, text: str) -> dict[str, Any]:
        """Format a text message payload.

        Args:
            text: Message text.

        Returns:
            DingTalk message payload.
        """
        return {
            "msgtype": "text",
            "text": {"content": text},
        }

    def _format_markdown_message(
        self,
        text: str,
        title: str = "Message",
    ) -> dict[str, Any]:
        """Format a markdown message payload.

        Args:
            text: Markdown content.
            title: Message title.

        Returns:
            DingTalk message payload.
        """
        normalized = normalize_dingtalk_markdown(text)
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": normalized,
            },
        }

    def _format_action_card(
        self,
        title: str,
        text: str,
        buttons: list[dict[str, str]] | None = None,
        single_url: str | None = None,
    ) -> dict[str, Any]:
        """Format an action card message.

        Args:
            title: Card title.
            text: Card content.
            buttons: Optional action buttons.
            single_url: Single action URL.

        Returns:
            DingTalk action card payload.
        """
        card: dict[str, Any] = {
            "title": title,
            "text": normalize_dingtalk_markdown(text),
        }

        if single_url:
            card["singleTitle"] = "View Details"
            card["singleURL"] = single_url
        elif buttons:
            card["btns"] = [
                {"title": btn["title"], "actionURL": btn["url"]} for btn in buttons
            ]
            card["btnOrientation"] = "0"

        return {"msgtype": "actionCard", "actionCard": card}

    async def _store_session_webhook(
        self,
        session_id: str,
        webhook_url: str,
    ) -> None:
        """Store session webhook for proactive messaging.

        Args:
            session_id: Session identifier.
            webhook_url: Session webhook URL.
        """
        async with self._webhook_lock:
            self._session_webhooks[session_id] = webhook_url

    async def _get_session_webhook(self, session_id: str) -> str | None:
        """Get stored session webhook.

        Args:
            session_id: Session identifier.

        Returns:
            Webhook URL or None.
        """
        async with self._webhook_lock:
            return self._session_webhooks.get(session_id)

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
        session_webhook = message.metadata.get("session_webhook")
        if session_webhook:
            await self._store_session_webhook(message.session_id, session_webhook)

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
                        {"session_id": message.session_id, "session_webhook": session_webhook},
                    )

            except Exception:
                logger.exception("Error processing DingTalk message")
                await self.send(
                    message.sender_id,
                    "An error occurred while processing your request.",
                    {"session_id": message.session_id, "session_webhook": session_webhook},
                )

    async def _process_dict_payload(self, payload: dict[str, Any]) -> None:
        """Process a dictionary payload.

        Args:
            payload: Dictionary payload.
        """
        session_webhook = payload.get("session_webhook")
        if session_webhook and payload.get("session_id"):
            await self._store_session_webhook(payload["session_id"], session_webhook)

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

        session_webhook = meta.get("session_webhook")
        if not session_webhook:
            session_id = meta.get("session_id", to_handle)
            session_webhook = await self._get_session_webhook(session_id)

        if len(full_text) > 3500:
            payload = self._format_text_message(full_text)
        else:
            title_preview = full_text[:20] + "..." if len(full_text) > 20 else full_text
            payload = self._format_markdown_message(full_text, f"💬 {title_preview}")

        await self._send_webhook(payload, session_webhook)

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

    async def send_action_card(
        self,
        to_handle: str,
        title: str,
        content: str,
        *,
        buttons: list[dict[str, str]] | None = None,
        single_url: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Send an action card message.

        Args:
            to_handle: Recipient identifier.
            title: Card title.
            content: Card content.
            buttons: Action buttons.
            single_url: Single action URL.
            meta: Optional metadata.

        Returns:
            True if sent successfully.
        """
        if not self.enabled:
            return False

        meta = meta or {}
        session_webhook = meta.get("session_webhook")
        if not session_webhook:
            session_id = meta.get("session_id", to_handle)
            session_webhook = await self._get_session_webhook(session_id)

        payload = self._format_action_card(title, content, buttons, single_url)
        return await self._send_webhook(payload, session_webhook)

    async def start(self) -> None:
        """Start the DingTalk channel."""
        if not self.enabled:
            logger.debug("DingTalk channel disabled")
            return

        self._running = True

        if self.client_id and self.client_secret:
            try:
                await self._get_access_token()
                logger.info("DingTalk access token obtained")
            except Exception:
                logger.exception("Failed to get DingTalk access token")

        logger.info("DingTalk channel started")

    async def stop(self) -> None:
        """Stop the DingTalk channel."""
        if not self.enabled:
            return

        self._running = False

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        logger.info("DingTalk channel stopped")

    async def health_check(self) -> dict[str, Any]:
        """Check channel health.

        Returns:
            Health status dictionary.
        """
        has_credentials = bool(self.client_id and self.client_secret)
        has_webhook = bool(self.webhook_url)

        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled and (has_credentials or has_webhook),
            "has_credentials": has_credentials,
            "has_webhook": has_webhook,
            "stored_sessions": len(self._session_webhooks),
        }
