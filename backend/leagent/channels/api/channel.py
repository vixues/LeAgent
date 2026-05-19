"""API channel implementation for LeAgent.

Provides REST callback functionality to external URLs with
webhook payload formatting for integration with external systems.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
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
    MessageStatus,
    MessageType,
)
from ..renderer import MessageRenderer, RenderStyle

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 1


class WebhookPayload:
    """Webhook payload formatter for API callbacks."""

    @staticmethod
    def format_message(
        message: ChannelMessage,
        *,
        include_metadata: bool = True,
    ) -> dict[str, Any]:
        """Format a channel message as webhook payload.

        Args:
            message: Message to format.
            include_metadata: Whether to include metadata.

        Returns:
            Formatted payload dictionary.
        """
        payload = {
            "id": message.id,
            "type": "message",
            "channel": message.channel_type.value,
            "message_type": message.message_type.value,
            "content": message.content,
            "sender_id": message.sender_id,
            "recipient_id": message.recipient_id,
            "session_id": message.session_id,
            "status": message.status.value,
            "created_at": message.created_at.isoformat(),
            "timestamp": datetime.utcnow().isoformat(),
        }

        if include_metadata and message.metadata:
            payload["metadata"] = message.metadata

        return payload

    @staticmethod
    def format_event(
        event: ChannelEvent,
        *,
        include_data: bool = True,
    ) -> dict[str, Any]:
        """Format a channel event as webhook payload.

        Args:
            event: Event to format.
            include_data: Whether to include event data.

        Returns:
            Formatted payload dictionary.
        """
        payload = {
            "id": event.id,
            "type": "event",
            "event_type": event.event_type,
            "channel": event.channel_type.value,
            "session_id": event.session_id,
            "timestamp": event.timestamp.isoformat(),
        }

        if include_data:
            payload["data"] = event.data

        return payload

    @staticmethod
    def format_text(
        text: str,
        *,
        session_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Format plain text as webhook payload.

        Args:
            text: Text content.
            session_id: Session identifier.
            user_id: User identifier.
            metadata: Optional metadata.

        Returns:
            Formatted payload dictionary.
        """
        return {
            "id": str(uuid4()),
            "type": "text",
            "content": text,
            "session_id": session_id,
            "user_id": user_id,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
        }


class CallbackEndpoint:
    """Represents a configured callback endpoint."""

    def __init__(
        self,
        url: str,
        *,
        secret: str = "",
        headers: dict[str, str] | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        """Initialize callback endpoint.

        Args:
            url: Callback URL.
            secret: Signature secret.
            headers: Custom headers.
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts.
            retry_delay: Delay between retries.
        """
        self.url = url
        self.secret = secret
        self.headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def generate_signature(self, payload: str, timestamp: str) -> str:
        """Generate HMAC signature for payload.

        Args:
            payload: JSON payload string.
            timestamp: Unix timestamp.

        Returns:
            Hex digest of HMAC signature.
        """
        if not self.secret:
            return ""

        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            self.secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def to_dict(self) -> dict[str, Any]:
        """Convert endpoint to dictionary.

        Returns:
            Endpoint configuration dictionary.
        """
        return {
            "url": self.url,
            "has_secret": bool(self.secret),
            "headers": list(self.headers.keys()),
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }


class APIChannel(BaseChannel):
    """API channel for REST callbacks to external systems.

    Delivers messages and events via HTTP POST to configured
    callback URLs with signature verification support.
    """

    channel_type = ChannelType.API
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        default_callback_url: str = "",
        callback_secret: str = "",
        custom_headers: dict[str, str] | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        bot_prefix: str = "",
        process_handler: Any | None = None,
    ) -> None:
        """Initialize API channel.

        Args:
            enabled: Whether channel is active.
            default_callback_url: Default callback URL.
            callback_secret: Signature secret.
            custom_headers: Custom request headers.
            timeout: Request timeout.
            max_retries: Maximum retries.
            bot_prefix: Prefix for messages.
            process_handler: Message processing handler.
        """
        super().__init__(
            enabled=enabled,
            bot_prefix=bot_prefix,
            process_handler=process_handler,
        )

        self._default_endpoint = CallbackEndpoint(
            url=default_callback_url,
            secret=callback_secret,
            headers=custom_headers,
            timeout=timeout,
            max_retries=max_retries,
        )

        self._session_endpoints: dict[str, CallbackEndpoint] = {}
        self._endpoint_lock = asyncio.Lock()
        self._http_session: Any = None

        self._renderer = MessageRenderer(
            RenderStyle(
                supports_markdown=True,
                supports_code_fence=True,
                supports_html=True,
                use_emoji=True,
            )
        )

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        process_handler: Any | None = None,
    ) -> APIChannel:
        """Create API channel from configuration.

        Args:
            config: Configuration dictionary.
            process_handler: Message processing handler.

        Returns:
            APIChannel instance.
        """
        return cls(
            enabled=config.get("enabled", True),
            default_callback_url=config.get("callback_url", ""),
            callback_secret=config.get("callback_secret", ""),
            custom_headers=config.get("headers", {}),
            timeout=config.get("timeout", DEFAULT_TIMEOUT_SECONDS),
            max_retries=config.get("max_retries", DEFAULT_MAX_RETRIES),
            bot_prefix=config.get("bot_prefix", ""),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> APIChannel:
        """Create API channel from environment variables.

        Args:
            process_handler: Message processing handler.

        Returns:
            APIChannel instance.
        """
        headers_str = os.getenv("API_CHANNEL_HEADERS", "")
        headers = {}
        if headers_str:
            try:
                headers = json.loads(headers_str)
            except json.JSONDecodeError:
                pass

        return cls(
            enabled=os.getenv("API_CHANNEL_ENABLED", "1") == "1",
            default_callback_url=os.getenv("API_CALLBACK_URL", ""),
            callback_secret=os.getenv("API_CALLBACK_SECRET", ""),
            custom_headers=headers,
            timeout=int(os.getenv("API_CALLBACK_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))),
            max_retries=int(os.getenv("API_CALLBACK_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))),
            bot_prefix=os.getenv("API_BOT_PREFIX", ""),
            process_handler=process_handler,
        )

    async def _get_http_session(self) -> Any:
        """Get or create HTTP session."""
        if self._http_session is None:
            try:
                import aiohttp

                self._http_session = aiohttp.ClientSession()
            except ImportError:
                logger.error("aiohttp not installed for API channel")
                raise
        return self._http_session

    async def register_callback(
        self,
        session_id: str,
        url: str,
        *,
        secret: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Register a callback endpoint for a session.

        Args:
            session_id: Session identifier.
            url: Callback URL.
            secret: Signature secret.
            headers: Custom headers.
        """
        endpoint = CallbackEndpoint(
            url=url,
            secret=secret or self._default_endpoint.secret,
            headers=headers or self._default_endpoint.headers,
            timeout=self._default_endpoint.timeout,
            max_retries=self._default_endpoint.max_retries,
        )

        async with self._endpoint_lock:
            self._session_endpoints[session_id] = endpoint

        logger.debug("Callback registered", session_id=session_id, url=url)

    async def unregister_callback(self, session_id: str) -> bool:
        """Unregister a callback endpoint.

        Args:
            session_id: Session identifier.

        Returns:
            True if endpoint was removed.
        """
        async with self._endpoint_lock:
            if session_id in self._session_endpoints:
                del self._session_endpoints[session_id]
                return True
        return False

    async def _get_endpoint(self, session_id: str) -> CallbackEndpoint:
        """Get endpoint for a session.

        Args:
            session_id: Session identifier.

        Returns:
            Callback endpoint.
        """
        async with self._endpoint_lock:
            return self._session_endpoints.get(session_id, self._default_endpoint)

    async def _send_callback(
        self,
        endpoint: CallbackEndpoint,
        payload: dict[str, Any],
    ) -> bool:
        """Send callback to endpoint with retries.

        Args:
            endpoint: Target endpoint.
            payload: Payload to send.

        Returns:
            True if sent successfully.
        """
        if not endpoint.url:
            logger.warning("No callback URL configured")
            return False

        http = await self._get_http_session()
        payload_str = json.dumps(payload, ensure_ascii=False, default=str)

        timestamp = str(int(time.time()))
        signature = endpoint.generate_signature(payload_str, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": timestamp,
            **endpoint.headers,
        }

        if signature:
            headers["X-Signature"] = signature

        for attempt in range(endpoint.max_retries):
            try:
                import aiohttp

                async with http.post(
                    endpoint.url,
                    data=payload_str,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=endpoint.timeout),
                ) as resp:
                    if resp.status < 400:
                        logger.debug(
                            "Callback sent",
                            url=endpoint.url,
                            status=resp.status,
                            attempt=attempt + 1,
                        )
                        return True

                    logger.warning(
                        "Callback failed",
                        url=endpoint.url,
                        status=resp.status,
                        attempt=attempt + 1,
                    )

            except asyncio.TimeoutError:
                logger.warning(
                    "Callback timeout",
                    url=endpoint.url,
                    timeout=endpoint.timeout,
                    attempt=attempt + 1,
                )

            except Exception as e:
                logger.error(
                    "Callback error",
                    url=endpoint.url,
                    error=str(e),
                    attempt=attempt + 1,
                )

            if attempt < endpoint.max_retries - 1:
                await asyncio.sleep(endpoint.retry_delay * (attempt + 1))

        return False

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
        callback_url = message.metadata.get("callback_url")
        if callback_url:
            await self.register_callback(
                message.session_id,
                callback_url,
                secret=message.metadata.get("callback_secret", ""),
                headers=message.metadata.get("callback_headers"),
            )

        if self._process_handler:
            try:
                async for event in self._process_handler(message):
                    if isinstance(event, ChannelEvent):
                        await self._send_event_callback(message.session_id, event)

            except Exception:
                logger.exception("Error processing API message")

        callback_payload = WebhookPayload.format_message(message)
        endpoint = await self._get_endpoint(message.session_id)
        await self._send_callback(endpoint, callback_payload)

    async def _process_dict_payload(self, payload: dict[str, Any]) -> None:
        """Process a dictionary payload."""
        session_id = payload.get("session_id", "")

        callback_url = payload.get("callback_url")
        if callback_url:
            await self.register_callback(
                session_id,
                callback_url,
                secret=payload.get("callback_secret", ""),
            )

        endpoint = await self._get_endpoint(session_id)
        await self._send_callback(endpoint, payload)

    async def _send_event_callback(
        self,
        session_id: str,
        event: ChannelEvent,
    ) -> None:
        """Send event callback.

        Args:
            session_id: Session identifier.
            event: Event to send.
        """
        payload = WebhookPayload.format_event(event)
        endpoint = await self._get_endpoint(session_id)
        await self._send_callback(endpoint, payload)

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send a text message via callback.

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

        session_id = meta.get("session_id", to_handle)

        callback_url = meta.get("callback_url")
        if callback_url:
            await self.register_callback(session_id, callback_url)

        payload = WebhookPayload.format_text(
            full_text,
            session_id=session_id,
            user_id=meta.get("user_id", ""),
            metadata=meta,
        )

        endpoint = await self._get_endpoint(session_id)
        await self._send_callback(endpoint, payload)

    async def send_event(
        self,
        *,
        user_id: str,
        session_id: str,
        event: ChannelEvent,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send an event via callback.

        Args:
            user_id: Target user ID.
            session_id: Target session ID.
            event: Event to send.
            meta: Optional metadata.
        """
        if not self.enabled:
            return

        meta = meta or {}
        callback_url = meta.get("callback_url")
        if callback_url:
            await self.register_callback(session_id, callback_url)

        await self._send_event_callback(session_id, event)

    async def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        secret: str = "",
        headers: dict[str, str] | None = None,
    ) -> bool:
        """Send a custom webhook payload.

        Args:
            url: Target URL.
            payload: Payload to send.
            secret: Signature secret.
            headers: Custom headers.

        Returns:
            True if sent successfully.
        """
        if not self.enabled:
            return False

        endpoint = CallbackEndpoint(
            url=url,
            secret=secret,
            headers=headers or {},
            timeout=self._default_endpoint.timeout,
            max_retries=self._default_endpoint.max_retries,
        )

        return await self._send_callback(endpoint, payload)

    async def start(self) -> None:
        """Start the API channel."""
        if not self.enabled:
            logger.debug("API channel disabled")
            return

        self._running = True
        logger.info("API channel started")

    async def stop(self) -> None:
        """Stop the API channel."""
        if not self.enabled:
            return

        self._running = False

        if self._http_session:
            await self._http_session.close()
            self._http_session = None

        logger.info("API channel stopped")

    async def health_check(self) -> dict[str, Any]:
        """Check channel health."""
        has_default_url = bool(self._default_endpoint.url)

        async with self._endpoint_lock:
            registered_sessions = len(self._session_endpoints)

        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled,
            "has_default_url": has_default_url,
            "registered_sessions": registered_sessions,
        }
