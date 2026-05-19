"""Notification Tool - Send notifications to various channels.

Provides multi-channel notification capabilities for DingTalk, Feishu,
WeChat Work, and other messaging platforms.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from enum import Enum
from typing import Any
from urllib.parse import quote_plus

import httpx
import structlog

from leagent.tools.base import (
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolProgressCallback,
    ToolResult,
)

logger = structlog.get_logger(__name__)

#: When workflow templates use ``channel: admin``, the URL is read from this
#: environment variable after remapping to ``webhook``. If unset, delivery
#: is skipped and execute returns ``skipped: true`` so error-handler paths do
#: not fail validation or double-fault on HTTP.
_LEAGENT_ADMIN_WEBHOOK_ENV = "LEAGENT_ADMIN_WEBHOOK_URL"


class NotificationChannel(str, Enum):
    """Supported notification channels."""

    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECHAT_WORK = "wechat_work"
    WEBHOOK = "webhook"
    SMS = "sms"


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageType(str, Enum):
    """Message types for notifications."""

    TEXT = "text"
    MARKDOWN = "markdown"
    CARD = "card"
    IMAGE = "image"
    FILE = "file"
    LINK = "link"


def normalize_workflow_notification_params(params: dict[str, Any]) -> dict[str, Any]:
    """Map legacy workflow payloads onto the notification JSON schema.

    * ``message`` → ``content`` when ``content`` is empty.
    * ``channel`` ``admin`` → ``webhook``; ``webhook_url`` from
      :envvar:`LEAGENT_ADMIN_WEBHOOK_URL` when missing. Empty URL sets
      ``_leagent_skip_notification`` for a no-op success in execute.
    * ``severity`` → ``priority`` when ``priority`` is missing (``medium`` →
      ``normal``, etc.).
    """
    out = dict(params)

    content = (out.get("content") or "").strip()
    if not content:
        msg = out.get("message")
        out["content"] = (str(msg).strip() if msg is not None else "") or "(no message)"
    else:
        out["content"] = content

    if not out.get("priority"):
        sev = str(out.get("severity") or "").lower().strip()
        sev_to_pri = {
            "low": NotificationPriority.LOW.value,
            "medium": NotificationPriority.NORMAL.value,
            "normal": NotificationPriority.NORMAL.value,
            "high": NotificationPriority.HIGH.value,
            "urgent": NotificationPriority.URGENT.value,
            "critical": NotificationPriority.URGENT.value,
        }
        if sev in sev_to_pri:
            out["priority"] = sev_to_pri[sev]

    if out.get("channel") == "admin":
        out["channel"] = NotificationChannel.WEBHOOK.value
        if not (out.get("webhook_url") or "").strip():
            out["webhook_url"] = (os.environ.get(_LEAGENT_ADMIN_WEBHOOK_ENV) or "").strip()
        if not (out.get("webhook_url") or "").strip():
            out["_leagent_skip_notification"] = True
        else:
            out.pop("_leagent_skip_notification", None)

    return out


class NotificationTool(BaseTool):
    """Tool for sending notifications to various channels.

    Features:
    - Multiple channels: DingTalk, Feishu, WeChat Work, Webhook
    - Message types: text, markdown, card, image, file, link
    - @mention support for users and groups
    - Priority levels with visual indicators
    - Webhook signing for security
    - Batch notifications

    Example:
        >>> tool = NotificationTool()
        >>> result = await tool.run({
        ...     "channel": "dingtalk",
        ...     "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
        ...     "message_type": "markdown",
        ...     "title": "Task Completed",
        ...     "content": "**Task**: Data Import\\n**Status**: Success",
        ...     "at_all": False,
        ...     "at_users": ["user1", "user2"]
        ... }, context)
    """

    name = "notification"
    description = (
        "Send notifications to channels like DingTalk, Feishu, WeChat Work. "
        "Supports text, markdown, cards, and @mentions with priority levels."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 30
    max_retries = 2
    aliases = ["notify", "dingtalk", "feishu", "wechat_work"]
    search_hint = "notification DingTalk Feishu WeChat Work send text markdown card mention"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        channel = (params or {}).get("channel", "")
        return f"Sending notification{f' via {channel}' if channel else ''}"

    async def run(
        self,
        params: dict[str, Any],
        context: ToolContext,
        *,
        on_progress: ToolProgressCallback | None = None,
    ) -> ToolResult:
        merged = normalize_workflow_notification_params(dict(params or {}))
        return await super().run(merged, context, on_progress=on_progress)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": [c.value for c in NotificationChannel],
                    "description": "Notification channel",
                },
                "webhook_url": {
                    "type": "string",
                    "description": "Webhook URL for the notification channel",
                },
                "secret": {
                    "type": "string",
                    "description": "Signing secret for webhook authentication",
                },
                "message_type": {
                    "type": "string",
                    "enum": [m.value for m in MessageType],
                    "default": "text",
                    "description": "Type of message to send",
                },
                "title": {
                    "type": "string",
                    "description": "Message title (for markdown/card types)",
                },
                "content": {
                    "type": "string",
                    "description": "Message content/body",
                },
                "priority": {
                    "type": "string",
                    "enum": [p.value for p in NotificationPriority],
                    "default": "normal",
                    "description": "Message priority level",
                },
                "at_all": {
                    "type": "boolean",
                    "description": "Mention all users in the group",
                    "default": False,
                },
                "at_users": {
                    "type": "array",
                    "description": "User IDs/phones to mention",
                    "items": {"type": "string"},
                },
                "at_mobiles": {
                    "type": "array",
                    "description": "Mobile numbers to mention (DingTalk)",
                    "items": {"type": "string"},
                },
                "image_url": {
                    "type": "string",
                    "description": "Image URL for image messages",
                },
                "link_url": {
                    "type": "string",
                    "description": "Link URL for link messages",
                },
                "link_pic_url": {
                    "type": "string",
                    "description": "Picture URL for link preview",
                },
                "card": {
                    "type": "object",
                    "description": "Card configuration for card messages",
                    "properties": {
                        "header": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "template": {"type": "string"},
                            },
                        },
                        "elements": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "actions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "url": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "extra_data": {
                    "type": "object",
                    "description": "Additional channel-specific data",
                },
            },
            "required": ["channel", "webhook_url", "content"],
        }

    def _get_priority_indicator(self, priority: str) -> str:
        """Get visual indicator for priority level."""
        indicators = {
            NotificationPriority.LOW.value: "🔵",
            NotificationPriority.NORMAL.value: "🟢",
            NotificationPriority.HIGH.value: "🟡",
            NotificationPriority.URGENT.value: "🔴",
        }
        return indicators.get(priority, "")

    def _sign_dingtalk(self, secret: str, timestamp: int) -> str:
        """Generate DingTalk webhook signature."""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return quote_plus(base64.b64encode(hmac_code))

    def _sign_feishu(self, secret: str, timestamp: int) -> str:
        """Generate Feishu webhook signature."""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        return base64.b64encode(hmac_code).decode()

    async def _send_dingtalk(
        self, params: dict[str, Any], client: httpx.AsyncClient
    ) -> dict[str, Any]:
        """Send notification to DingTalk."""
        webhook_url = params["webhook_url"]
        secret = params.get("secret")
        message_type = params.get("message_type", MessageType.TEXT.value)
        title = params.get("title", "")
        content = params["content"]
        priority = params.get("priority", NotificationPriority.NORMAL.value)
        at_all = params.get("at_all", False)
        at_users = params.get("at_users", [])
        at_mobiles = params.get("at_mobiles", [])

        if secret:
            timestamp = int(time.time() * 1000)
            sign = self._sign_dingtalk(secret, timestamp)
            if "?" in webhook_url:
                webhook_url += f"&timestamp={timestamp}&sign={sign}"
            else:
                webhook_url += f"?timestamp={timestamp}&sign={sign}"

        indicator = self._get_priority_indicator(priority)

        payload: dict[str, Any] = {}

        if message_type == MessageType.TEXT.value:
            text_content = content
            if indicator:
                text_content = f"{indicator} {content}"
            payload = {
                "msgtype": "text",
                "text": {"content": text_content},
                "at": {
                    "atMobiles": at_mobiles,
                    "atUserIds": at_users,
                    "isAtAll": at_all,
                },
            }

        elif message_type == MessageType.MARKDOWN.value:
            md_content = content
            if indicator and title:
                title = f"{indicator} {title}"
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title or "Notification",
                    "text": md_content,
                },
                "at": {
                    "atMobiles": at_mobiles,
                    "atUserIds": at_users,
                    "isAtAll": at_all,
                },
            }

        elif message_type == MessageType.LINK.value:
            payload = {
                "msgtype": "link",
                "link": {
                    "title": title or "Link",
                    "text": content,
                    "messageUrl": params.get("link_url", ""),
                    "picUrl": params.get("link_pic_url", ""),
                },
            }

        elif message_type == MessageType.CARD.value:
            card_config = params.get("card", {})
            actions = card_config.get("actions", [])
            btns = [{"title": a["title"], "actionURL": a["url"]} for a in actions]

            payload = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title or "Card",
                    "text": content,
                    "btns": btns,
                    "btnOrientation": "0",
                },
            }

        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        return response.json()

    async def _send_feishu(
        self, params: dict[str, Any], client: httpx.AsyncClient
    ) -> dict[str, Any]:
        """Send notification to Feishu."""
        webhook_url = params["webhook_url"]
        secret = params.get("secret")
        message_type = params.get("message_type", MessageType.TEXT.value)
        title = params.get("title", "")
        content = params["content"]
        priority = params.get("priority", NotificationPriority.NORMAL.value)
        at_all = params.get("at_all", False)
        at_users = params.get("at_users", [])

        indicator = self._get_priority_indicator(priority)

        payload: dict[str, Any] = {}

        if message_type == MessageType.TEXT.value:
            text_content = content
            if indicator:
                text_content = f"{indicator} {content}"

            if at_all:
                text_content += "\n<at user_id=\"all\">所有人</at>"
            for user_id in at_users:
                text_content += f"\n<at user_id=\"{user_id}\"></at>"

            payload = {
                "msg_type": "text",
                "content": {"text": text_content},
            }

        elif message_type == MessageType.MARKDOWN.value:
            md_title = title
            if indicator and md_title:
                md_title = f"{indicator} {md_title}"

            md_content = content
            if at_all:
                md_content += "\n<at user_id=\"all\">所有人</at>"
            for user_id in at_users:
                md_content += f"\n<at user_id=\"{user_id}\"></at>"

            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": md_title or "Notification"},
                        "template": self._get_feishu_header_color(priority),
                    },
                    "elements": [
                        {"tag": "markdown", "content": md_content}
                    ],
                },
            }

        elif message_type == MessageType.CARD.value:
            card_config = params.get("card", {})
            header = card_config.get("header", {})
            elements = card_config.get("elements", [])
            actions = card_config.get("actions", [])

            card_elements = []
            if content:
                card_elements.append({"tag": "markdown", "content": content})
            card_elements.extend(elements)

            if actions:
                action_elements = []
                for action in actions:
                    action_elements.append({
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": action.get("title", "Click")},
                        "url": action.get("url", ""),
                        "type": "primary",
                    })
                card_elements.append({"tag": "action", "actions": action_elements})

            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": header.get("title", title or "Notification"),
                        },
                        "template": header.get("template", self._get_feishu_header_color(priority)),
                    },
                    "elements": card_elements,
                },
            }

        elif message_type == MessageType.IMAGE.value:
            payload = {
                "msg_type": "image",
                "content": {"image_key": params.get("image_url", "")},
            }

        if secret:
            timestamp = int(time.time())
            sign = self._sign_feishu(secret, timestamp)
            payload["timestamp"] = str(timestamp)
            payload["sign"] = sign

        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        return response.json()

    def _get_feishu_header_color(self, priority: str) -> str:
        """Get Feishu card header color based on priority."""
        colors = {
            NotificationPriority.LOW.value: "blue",
            NotificationPriority.NORMAL.value: "green",
            NotificationPriority.HIGH.value: "yellow",
            NotificationPriority.URGENT.value: "red",
        }
        return colors.get(priority, "blue")

    async def _send_wechat_work(
        self, params: dict[str, Any], client: httpx.AsyncClient
    ) -> dict[str, Any]:
        """Send notification to WeChat Work."""
        webhook_url = params["webhook_url"]
        message_type = params.get("message_type", MessageType.TEXT.value)
        title = params.get("title", "")
        content = params["content"]
        priority = params.get("priority", NotificationPriority.NORMAL.value)
        at_users = params.get("at_users", [])
        at_mobiles = params.get("at_mobiles", [])

        indicator = self._get_priority_indicator(priority)

        payload: dict[str, Any] = {}

        if message_type == MessageType.TEXT.value:
            text_content = content
            if indicator:
                text_content = f"{indicator} {content}"

            payload = {
                "msgtype": "text",
                "text": {
                    "content": text_content,
                    "mentioned_list": at_users if at_users else None,
                    "mentioned_mobile_list": at_mobiles if at_mobiles else None,
                },
            }

        elif message_type == MessageType.MARKDOWN.value:
            md_content = content
            if indicator and title:
                md_content = f"## {indicator} {title}\n{content}"
            elif title:
                md_content = f"## {title}\n{content}"

            payload = {
                "msgtype": "markdown",
                "markdown": {"content": md_content},
            }

        elif message_type == MessageType.CARD.value:
            card_config = params.get("card", {})
            actions = card_config.get("actions", [])

            desc = content[:128] if len(content) > 128 else content
            card_title = title or "Notification"
            if indicator:
                card_title = f"{indicator} {card_title}"

            card_payload: dict[str, Any] = {
                "card_type": "text_notice",
                "main_title": {"title": card_title, "desc": desc},
            }

            if actions:
                card_payload["card_action"] = {
                    "type": 1,
                    "url": actions[0].get("url", ""),
                }

            payload = {
                "msgtype": "template_card",
                "template_card": card_payload,
            }

        elif message_type == MessageType.IMAGE.value:
            payload = {
                "msgtype": "image",
                "image": {"base64": params.get("image_url", ""), "md5": ""},
            }

        elif message_type == MessageType.FILE.value:
            payload = {
                "msgtype": "file",
                "file": {"media_id": params.get("extra_data", {}).get("media_id", "")},
            }

        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        return response.json()

    async def _send_webhook(
        self, params: dict[str, Any], client: httpx.AsyncClient
    ) -> dict[str, Any]:
        """Send notification to generic webhook."""
        webhook_url = params["webhook_url"]
        content = params["content"]
        title = params.get("title", "")
        priority = params.get("priority", NotificationPriority.NORMAL.value)
        extra_data = params.get("extra_data", {})

        payload = {
            "title": title,
            "content": content,
            "priority": priority,
            "timestamp": int(time.time()),
            **extra_data,
        }

        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()

        try:
            return response.json()
        except Exception:
            return {"status": "sent", "response": response.text}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Send notification to specified channel.

        Args:
            params: Notification parameters including channel, webhook, and content.
            context: Tool execution context.

        Returns:
            Dictionary containing send status and response.

        Raises:
            ValueError: If channel is not supported.
            httpx.HTTPError: If webhook request fails.
        """
        params = normalize_workflow_notification_params(dict(params))

        if params.get("_leagent_skip_notification"):
            logger.info(
                "notification_skipped_no_admin_webhook",
                env_var=_LEAGENT_ADMIN_WEBHOOK_ENV,
            )
            return {
                "success": True,
                "channel": NotificationChannel.WEBHOOK.value,
                "skipped": True,
                "message_type": params.get("message_type", "text"),
                "priority": params.get("priority", "normal"),
                "response": None,
                "error": None,
            }

        channel = params["channel"]

        logger.info(
            "Sending notification",
            channel=channel,
            message_type=params.get("message_type", "text"),
            priority=params.get("priority", "normal"),
        )

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            if channel == NotificationChannel.DINGTALK.value:
                response = await self._send_dingtalk(params, client)
            elif channel == NotificationChannel.FEISHU.value:
                response = await self._send_feishu(params, client)
            elif channel == NotificationChannel.WECHAT_WORK.value:
                response = await self._send_wechat_work(params, client)
            elif channel == NotificationChannel.WEBHOOK.value:
                response = await self._send_webhook(params, client)
            else:
                raise ValueError(f"Unsupported notification channel: {channel}")

        success = True
        error_msg = None

        if channel == NotificationChannel.DINGTALK.value:
            if response.get("errcode", 0) != 0:
                success = False
                error_msg = response.get("errmsg", "Unknown error")
        elif channel == NotificationChannel.FEISHU.value:
            if response.get("code", 0) != 0:
                success = False
                error_msg = response.get("msg", "Unknown error")
        elif channel == NotificationChannel.WECHAT_WORK.value:
            if response.get("errcode", 0) != 0:
                success = False
                error_msg = response.get("errmsg", "Unknown error")

        logger.info(
            "Notification sent",
            channel=channel,
            success=success,
            error=error_msg,
        )

        return {
            "success": success,
            "channel": channel,
            "message_type": params.get("message_type", "text"),
            "priority": params.get("priority", "normal"),
            "response": response,
            "error": error_msg,
        }


class BatchNotificationTool(BaseTool):
    """Tool for sending batch notifications to multiple channels.

    Example:
        >>> tool = BatchNotificationTool()
        >>> result = await tool.run({
        ...     "notifications": [
        ...         {"channel": "dingtalk", "webhook_url": "...", "content": "..."},
        ...         {"channel": "feishu", "webhook_url": "...", "content": "..."},
        ...     ]
        ... }, context)
    """

    name = "batch_notification"
    description = (
        "Send batch notifications to multiple channels. Useful for alerting "
        "across different platforms simultaneously."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 60
    max_retries = 1
    aliases = ["batch_notify", "multi_channel_notify"]
    search_hint = "notification batch multi-channel alert broadcast"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        count = len((params or {}).get("channels", []))
        return f"Sending notifications to {count} channels"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "notifications": {
                    "type": "array",
                    "description": "List of notifications to send",
                    "items": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "enum": [c.value for c in NotificationChannel],
                            },
                            "webhook_url": {"type": "string"},
                            "secret": {"type": "string"},
                            "message_type": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "priority": {"type": "string"},
                            "at_all": {"type": "boolean"},
                            "at_users": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["channel", "webhook_url", "content"],
                    },
                },
                "stop_on_error": {
                    "type": "boolean",
                    "default": False,
                },
            },
            "required": ["notifications"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Send batch notifications.

        Args:
            params: Batch notification parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing batch send results.
        """
        notifications = params["notifications"]
        stop_on_error = params.get("stop_on_error", False)

        notification_tool = NotificationTool()
        results: list[dict[str, Any]] = []
        success_count = 0
        failed_count = 0

        for notification in notifications:
            merged = normalize_workflow_notification_params(dict(notification))
            try:
                result = await notification_tool.execute(merged, context)
                results.append(result)

                if result.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
                    if stop_on_error:
                        break

            except Exception as e:
                logger.error(
                    "Notification failed",
                    channel=merged.get("channel"),
                    error=str(e),
                )
                results.append({
                    "success": False,
                    "channel": merged.get("channel"),
                    "error": str(e),
                })
                failed_count += 1

                if stop_on_error:
                    break

        return {
            "success": failed_count == 0,
            "statistics": {
                "total": len(notifications),
                "success": success_count,
                "failed": failed_count,
            },
            "results": results,
        }
