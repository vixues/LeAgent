"""WeChat Work channel implementation for LeAgent.

Provides WeChat Work (企业微信) webhook integration with
markdown message support for enterprise communication.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from datetime import datetime
from typing import Any

import structlog

from ..base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from ..renderer import MessageRenderer, RenderStyle, normalize_wechat_markdown

logger = structlog.get_logger(__name__)

WECHAT_WORK_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
WECHAT_WORK_TOKEN_TTL_SECONDS = 7200
WECHAT_WORK_MAX_TEXT_LENGTH = 2048


class WeChatWorkChannel(BaseChannel):
    """WeChat Work channel for enterprise messaging.

    Supports webhook messaging with markdown support and
    mentions for group conversations.
    """

    channel_type = ChannelType.WECHAT_WORK
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        corp_id: str = "",
        corp_secret: str = "",
        agent_id: str = "",
        webhook_url: str = "",
        bot_prefix: str = "",
        process_handler: Any | None = None,
    ) -> None:
        """Initialize WeChat Work channel.

        Args:
            enabled: Whether channel is active.
            corp_id: Enterprise corp ID.
            corp_secret: App secret.
            agent_id: App agent ID.
            webhook_url: Bot webhook URL.
            bot_prefix: Prefix for bot messages.
            process_handler: Message processing handler.
        """
        super().__init__(
            enabled=enabled,
            bot_prefix=bot_prefix,
            process_handler=process_handler,
        )
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.agent_id = agent_id
        self.webhook_url = webhook_url

        self._token_value: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._http_session: Any = None

        self._renderer = MessageRenderer(
            RenderStyle(
                supports_markdown=True,
                supports_code_fence=False,
                max_length=WECHAT_WORK_MAX_TEXT_LENGTH,
                use_emoji=True,
            )
        )

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: Any | None = None,
    ) -> WeChatWorkChannel:
        """Create WeChat Work channel from configuration.

        Args:
            config: Configuration dictionary.
            process_handler: Message processing handler.

        Returns:
            WeChatWorkChannel instance.
        """
        return cls(
            enabled=config.get("enabled", True),
            corp_id=config.get("corp_id", ""),
            corp_secret=config.get("corp_secret", ""),
            agent_id=config.get("agent_id", ""),
            webhook_url=config.get("webhook_url", ""),
            bot_prefix=config.get("bot_prefix", ""),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> WeChatWorkChannel:
        """Create WeChat Work channel from environment variables.

        Args:
            process_handler: Message processing handler.

        Returns:
            WeChatWorkChannel instance.
        """
        return cls(
            enabled=os.getenv("WECHAT_WORK_CHANNEL_ENABLED", "1") == "1",
            corp_id=os.getenv("WECHAT_WORK_CORP_ID", ""),
            corp_secret=os.getenv("WECHAT_WORK_CORP_SECRET", ""),
            agent_id=os.getenv("WECHAT_WORK_AGENT_ID", ""),
            webhook_url=os.getenv("WECHAT_WORK_WEBHOOK_URL", ""),
            bot_prefix=os.getenv("WECHAT_WORK_BOT_PREFIX", ""),
            process_handler=process_handler,
        )

    async def _get_http_session(self) -> Any:
        """Get or create HTTP session."""
        if self._http_session is None:
            try:
                import aiohttp

                self._http_session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed for WeChat Work channel")
                raise
        return self._http_session

    async def _get_access_token(self) -> str:
        """Get and cache WeChat Work access token.

        Returns:
            Access token string.
        """
        if not self.corp_id or not self.corp_secret:
            raise RuntimeError("WeChat Work corp_id and corp_secret required")

        now = time.time()
        if self._token_value and now < self._token_expires_at:
            return self._token_value

        async with self._token_lock:
            now = time.time()
            if self._token_value and now < self._token_expires_at:
                return self._token_value

            http = await self._get_http_session()
            url = f"{WECHAT_WORK_API_BASE}/gettoken"
            params = {
                "corpid": self.corp_id,
                "corpsecret": self.corp_secret,
            }

            async with http.get(url, params=params) as resp:
                data = await resp.json()

                if data.get("errcode", 0) != 0:
                    raise RuntimeError(f"Failed to get WeChat Work token: {data}")

            token = data.get("access_token")
            expires_in = data.get("expires_in", WECHAT_WORK_TOKEN_TTL_SECONDS)

            self._token_value = token
            self._token_expires_at = now + expires_in - 60
            return token

    async def _send_webhook(self, data: dict[str, Any]) -> bool:
        """Send message via webhook.

        Args:
            data: Message payload.

        Returns:
            True if sent successfully.
        """
        if not self.webhook_url:
            logger.warning("No webhook URL configured for WeChat Work")
            return False

        http = await self._get_http_session()

        try:
            async with http.post(
                self.webhook_url,
                json=data,
                headers={"Content-Type": "application/json"},
            ) as resp:
                result = await resp.json()

                if resp.status >= 400 or result.get("errcode", 0) != 0:
                    logger.error(
                        "WeChat Work webhook failed",
                        status=resp.status,
                        response=result,
                    )
                    return False

                return True

        except Exception as e:
            logger.exception("WeChat Work webhook error", error=str(e))
            return False

    async def _send_message_api(
        self,
        user_ids: list[str],
        msg_type: str,
        content: dict[str, Any],
    ) -> bool:
        """Send message via WeChat Work API.

        Args:
            user_ids: List of target user IDs.
            msg_type: Message type.
            content: Message content.

        Returns:
            True if sent successfully.
        """
        try:
            token = await self._get_access_token()
        except Exception:
            logger.exception("Failed to get WeChat Work token")
            return False

        http = await self._get_http_session()
        url = f"{WECHAT_WORK_API_BASE}/message/send"
        params = {"access_token": token}

        payload = {
            "touser": "|".join(user_ids) if user_ids else "@all",
            "msgtype": msg_type,
            "agentid": self.agent_id,
            **content,
        }

        try:
            async with http.post(url, params=params, json=payload) as resp:
                result = await resp.json()

                if resp.status >= 400 or result.get("errcode", 0) != 0:
                    logger.error(
                        "WeChat Work API send failed",
                        status=resp.status,
                        response=result,
                    )
                    return False

                return True

        except Exception as e:
            logger.exception("WeChat Work API error", error=str(e))
            return False

    def _format_text_message(self, text: str) -> dict[str, Any]:
        """Format a text message payload.

        Args:
            text: Message text.

        Returns:
            WeChat Work message payload.
        """
        return {
            "msgtype": "text",
            "text": {"content": text},
        }

    def _format_markdown_message(
        self,
        text: str,
        mentioned_list: list[str] | None = None,
    ) -> dict[str, Any]:
        """Format a markdown message payload.

        Args:
            text: Markdown content.
            mentioned_list: List of user IDs to mention.

        Returns:
            WeChat Work message payload.
        """
        normalized = normalize_wechat_markdown(text)

        payload: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {"content": normalized},
        }

        if mentioned_list:
            payload["markdown"]["mentioned_list"] = mentioned_list

        return payload

    def _format_news_message(
        self,
        articles: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Format a news/card message payload.

        Args:
            articles: List of article items.

        Returns:
            WeChat Work news message payload.
        """
        return {
            "msgtype": "news",
            "news": {
                "articles": [
                    {
                        "title": article.get("title", ""),
                        "description": article.get("description", ""),
                        "url": article.get("url", ""),
                        "picurl": article.get("picurl", ""),
                    }
                    for article in articles
                ]
            },
        }

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
                        {"session_id": message.session_id},
                    )

            except Exception:
                logger.exception("Error processing WeChat Work message")

    async def _process_dict_payload(self, payload: dict[str, Any]) -> None:
        """Process a dictionary payload."""
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

        if len(full_text) > WECHAT_WORK_MAX_TEXT_LENGTH:
            full_text = full_text[: WECHAT_WORK_MAX_TEXT_LENGTH - 3] + "..."

        mentioned = meta.get("mentioned_list")

        if self.webhook_url:
            payload = self._format_markdown_message(full_text, mentioned)
            await self._send_webhook(payload)
        elif self.corp_id and self.agent_id:
            user_ids = [to_handle] if to_handle and to_handle != "broadcast" else []
            content = {"text": {"content": full_text}}
            await self._send_message_api(user_ids, "text", content)

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

    async def send_news(
        self,
        articles: list[dict[str, str]],
        *,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Send a news/card message.

        Args:
            articles: List of article items.
            meta: Optional metadata.

        Returns:
            True if sent successfully.
        """
        if not self.enabled:
            return False

        payload = self._format_news_message(articles)
        return await self._send_webhook(payload)

    async def start(self) -> None:
        """Start the WeChat Work channel."""
        if not self.enabled:
            logger.debug("WeChat Work channel disabled")
            return

        self._running = True

        if self.corp_id and self.corp_secret:
            try:
                await self._get_access_token()
                logger.info("WeChat Work access token obtained")
            except Exception:
                logger.exception("Failed to get WeChat Work access token")

        logger.info("WeChat Work channel started")

    async def stop(self) -> None:
        """Stop the WeChat Work channel."""
        if not self.enabled:
            return

        self._running = False

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        logger.info("WeChat Work channel stopped")

    async def health_check(self) -> dict[str, Any]:
        """Check channel health."""
        has_credentials = bool(self.corp_id and self.corp_secret and self.agent_id)
        has_webhook = bool(self.webhook_url)

        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled and (has_credentials or has_webhook),
            "has_credentials": has_credentials,
            "has_webhook": has_webhook,
        }
