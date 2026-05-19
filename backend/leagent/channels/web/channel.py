"""Web channel implementation for LeAgent.

Provides WebSocket connection management and SSE streaming support
for real-time web-based communication.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from ..base import (
    BaseChannel,
    ChannelEvent,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from ..renderer import MessageRenderer, RenderStyle

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger(__name__)


class WebSocketConnection:
    """Represents an active WebSocket connection."""

    def __init__(
        self,
        connection_id: str,
        user_id: str,
        session_id: str,
        websocket: Any,
    ) -> None:
        """Initialize WebSocket connection.

        Args:
            connection_id: Unique connection identifier.
            user_id: Associated user ID.
            session_id: Associated session ID.
            websocket: WebSocket object.
        """
        self.connection_id = connection_id
        self.user_id = user_id
        self.session_id = session_id
        self.websocket = websocket
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self._closed = False

    async def send(self, data: dict[str, Any]) -> bool:
        """Send data through the WebSocket.

        Args:
            data: Data to send as JSON.

        Returns:
            True if sent successfully.
        """
        if self._closed:
            return False

        try:
            await self.websocket.send_json(data)
            self.last_activity = datetime.utcnow()
            return True
        except Exception as e:
            logger.debug("WebSocket send failed", error=str(e))
            self._closed = True
            return False

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self._closed:
            return

        self._closed = True
        try:
            await self.websocket.close()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        """Check if connection is still active."""
        return not self._closed


class SSEStream:
    """Server-Sent Events stream for a client."""

    def __init__(
        self,
        stream_id: str,
        user_id: str,
        session_id: str,
    ) -> None:
        """Initialize SSE stream.

        Args:
            stream_id: Unique stream identifier.
            user_id: Associated user ID.
            session_id: Associated session ID.
        """
        self.stream_id = stream_id
        self.user_id = user_id
        self.session_id = session_id
        self.created_at = datetime.utcnow()
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._closed = False

    async def push(self, data: dict[str, Any]) -> bool:
        """Push data to the SSE stream.

        Args:
            data: Event data to push.

        Returns:
            True if pushed successfully.
        """
        if self._closed:
            return False

        try:
            await self._queue.put(data)
            return True
        except Exception:
            return False

    async def iterate(self) -> AsyncIterator[str]:
        """Iterate over SSE events.

        Yields:
            SSE-formatted event strings.
        """
        while not self._closed:
            try:
                data = await asyncio.wait_for(self._queue.get(), timeout=30.0)
                if data is None:
                    break

                event_type = data.get("event", "message")
                event_data = json.dumps(data.get("data", data))

                yield f"event: {event_type}\ndata: {event_data}\n\n"

            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
            except asyncio.CancelledError:
                break

    async def close(self) -> None:
        """Close the SSE stream."""
        if self._closed:
            return

        self._closed = True
        await self._queue.put(None)

    @property
    def is_active(self) -> bool:
        """Check if stream is still active."""
        return not self._closed


class ConnectionManager:
    """Manages WebSocket connections and SSE streams."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        self._websockets: dict[str, WebSocketConnection] = {}
        self._sse_streams: dict[str, SSEStream] = {}
        self._user_connections: dict[str, set[str]] = {}
        self._session_connections: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def register_websocket(
        self,
        user_id: str,
        session_id: str,
        websocket: Any,
    ) -> WebSocketConnection:
        """Register a new WebSocket connection.

        Args:
            user_id: User identifier.
            session_id: Session identifier.
            websocket: WebSocket object.

        Returns:
            WebSocketConnection instance.
        """
        connection_id = str(uuid4())
        connection = WebSocketConnection(
            connection_id=connection_id,
            user_id=user_id,
            session_id=session_id,
            websocket=websocket,
        )

        async with self._lock:
            self._websockets[connection_id] = connection

            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(connection_id)

            if session_id not in self._session_connections:
                self._session_connections[session_id] = set()
            self._session_connections[session_id].add(connection_id)

        logger.debug(
            "WebSocket registered",
            connection_id=connection_id,
            user_id=user_id,
            session_id=session_id,
        )

        return connection

    async def unregister_websocket(self, connection_id: str) -> None:
        """Unregister a WebSocket connection.

        Args:
            connection_id: Connection identifier.
        """
        async with self._lock:
            connection = self._websockets.pop(connection_id, None)
            if not connection:
                return

            if connection.user_id in self._user_connections:
                self._user_connections[connection.user_id].discard(connection_id)
                if not self._user_connections[connection.user_id]:
                    del self._user_connections[connection.user_id]

            if connection.session_id in self._session_connections:
                self._session_connections[connection.session_id].discard(connection_id)
                if not self._session_connections[connection.session_id]:
                    del self._session_connections[connection.session_id]

        await connection.close()
        logger.debug("WebSocket unregistered", connection_id=connection_id)

    async def create_sse_stream(
        self,
        user_id: str,
        session_id: str,
    ) -> SSEStream:
        """Create a new SSE stream.

        Args:
            user_id: User identifier.
            session_id: Session identifier.

        Returns:
            SSEStream instance.
        """
        stream_id = str(uuid4())
        stream = SSEStream(
            stream_id=stream_id,
            user_id=user_id,
            session_id=session_id,
        )

        async with self._lock:
            self._sse_streams[stream_id] = stream

        logger.debug(
            "SSE stream created",
            stream_id=stream_id,
            user_id=user_id,
            session_id=session_id,
        )

        return stream

    async def close_sse_stream(self, stream_id: str) -> None:
        """Close an SSE stream.

        Args:
            stream_id: Stream identifier.
        """
        async with self._lock:
            stream = self._sse_streams.pop(stream_id, None)

        if stream:
            await stream.close()
            logger.debug("SSE stream closed", stream_id=stream_id)

    async def send_to_user(
        self,
        user_id: str,
        data: dict[str, Any],
    ) -> int:
        """Send data to all connections for a user.

        Args:
            user_id: Target user ID.
            data: Data to send.

        Returns:
            Number of successful sends.
        """
        sent = 0

        async with self._lock:
            connection_ids = list(self._user_connections.get(user_id, set()))
            stream_ids = [
                sid
                for sid, stream in self._sse_streams.items()
                if stream.user_id == user_id
            ]

        for conn_id in connection_ids:
            conn = self._websockets.get(conn_id)
            if conn and await conn.send(data):
                sent += 1

        for stream_id in stream_ids:
            stream = self._sse_streams.get(stream_id)
            if stream and await stream.push(data):
                sent += 1

        return sent

    async def send_to_session(
        self,
        session_id: str,
        data: dict[str, Any],
    ) -> int:
        """Send data to all connections for a session.

        Args:
            session_id: Target session ID.
            data: Data to send.

        Returns:
            Number of successful sends.
        """
        sent = 0

        async with self._lock:
            connection_ids = list(self._session_connections.get(session_id, set()))
            stream_ids = [
                sid
                for sid, stream in self._sse_streams.items()
                if stream.session_id == session_id
            ]

        for conn_id in connection_ids:
            conn = self._websockets.get(conn_id)
            if conn and await conn.send(data):
                sent += 1

        for stream_id in stream_ids:
            stream = self._sse_streams.get(stream_id)
            if stream and await stream.push(data):
                sent += 1

        return sent

    async def broadcast(self, data: dict[str, Any]) -> int:
        """Broadcast data to all connections.

        Args:
            data: Data to broadcast.

        Returns:
            Number of successful sends.
        """
        sent = 0

        async with self._lock:
            connections = list(self._websockets.values())
            streams = list(self._sse_streams.values())

        for conn in connections:
            if await conn.send(data):
                sent += 1

        for stream in streams:
            if await stream.push(data):
                sent += 1

        return sent

    async def cleanup_stale(self, max_age_seconds: int = 3600) -> int:
        """Remove stale connections.

        Args:
            max_age_seconds: Maximum idle time before removal.

        Returns:
            Number of connections removed.
        """
        removed = 0
        now = datetime.utcnow()

        async with self._lock:
            stale_ws = [
                conn_id
                for conn_id, conn in self._websockets.items()
                if not conn.is_connected
                or (now - conn.last_activity).total_seconds() > max_age_seconds
            ]

            stale_sse = [
                stream_id
                for stream_id, stream in self._sse_streams.items()
                if not stream.is_active
            ]

        for conn_id in stale_ws:
            await self.unregister_websocket(conn_id)
            removed += 1

        for stream_id in stale_sse:
            await self.close_sse_stream(stream_id)
            removed += 1

        if removed:
            logger.debug("Cleaned up stale connections", count=removed)

        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get connection statistics.

        Returns:
            Statistics dictionary.
        """
        return {
            "websocket_connections": len(self._websockets),
            "sse_streams": len(self._sse_streams),
            "unique_users": len(self._user_connections),
            "unique_sessions": len(self._session_connections),
        }


_connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance.

    Returns:
        ConnectionManager instance.
    """
    return _connection_manager


class WebChannel(BaseChannel):
    """Web channel for WebSocket and SSE communication.

    Manages real-time web connections and provides streaming
    message delivery.
    """

    channel_type = ChannelType.WEB
    uses_manager_queue = True

    def __init__(
        self,
        *,
        enabled: bool = True,
        bot_prefix: str = "",
        process_handler: Any | None = None,
        cleanup_interval: int = 300,
        connection_timeout: int = 3600,
    ) -> None:
        """Initialize web channel.

        Args:
            enabled: Whether channel is active.
            bot_prefix: Prefix for bot messages.
            process_handler: Message processing handler.
            cleanup_interval: Seconds between cleanup runs.
            connection_timeout: Max idle time for connections.
        """
        super().__init__(
            enabled=enabled,
            bot_prefix=bot_prefix,
            process_handler=process_handler,
        )
        self._cleanup_interval = cleanup_interval
        self._connection_timeout = connection_timeout
        self._cleanup_task: asyncio.Task[None] | None = None
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
    ) -> WebChannel:
        """Create web channel from configuration.

        Args:
            config: Configuration dictionary.
            process_handler: Message processing handler.

        Returns:
            WebChannel instance.
        """
        return cls(
            enabled=config.get("enabled", True),
            bot_prefix=config.get("bot_prefix", ""),
            cleanup_interval=config.get("cleanup_interval", 300),
            connection_timeout=config.get("connection_timeout", 3600),
            process_handler=process_handler,
        )

    @classmethod
    def from_env(cls, process_handler: Any | None = None) -> WebChannel:
        """Create web channel from environment variables.

        Args:
            process_handler: Message processing handler.

        Returns:
            WebChannel instance.
        """
        return cls(
            enabled=os.getenv("WEB_CHANNEL_ENABLED", "1") == "1",
            bot_prefix=os.getenv("WEB_BOT_PREFIX", ""),
            cleanup_interval=int(os.getenv("WEB_CLEANUP_INTERVAL", "300")),
            connection_timeout=int(os.getenv("WEB_CONNECTION_TIMEOUT", "3600")),
            process_handler=process_handler,
        )

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
        session_id = message.session_id or message.sender_id

        if self._process_handler:
            try:
                async for event in self._process_handler(message):
                    await self._send_to_session(session_id, event)
            except Exception:
                logger.exception("Error processing web message")
                await _connection_manager.send_to_session(
                    session_id,
                    {
                        "type": "error",
                        "content": "An error occurred while processing.",
                    },
                )
        else:
            await _connection_manager.send_to_session(
                session_id,
                {
                    "type": "message",
                    "content": message.content,
                },
            )

    async def _process_dict_payload(self, payload: dict[str, Any]) -> None:
        """Process a dictionary payload.

        Args:
            payload: Dictionary payload.
        """
        session_id = payload.get("session_id", "")
        if session_id:
            await _connection_manager.send_to_session(session_id, payload)

    async def _send_to_session(self, session_id: str, event: Any) -> None:
        """Send event to a session.

        Args:
            session_id: Target session.
            event: Event to send.
        """
        if isinstance(event, ChannelEvent):
            data = event.to_dict()
        elif isinstance(event, dict):
            data = event
        else:
            data = {"type": "message", "data": str(event)}

        await _connection_manager.send_to_session(session_id, data)

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Send a text message.

        Args:
            to_handle: Recipient identifier (session_id).
            text: Message text.
            meta: Optional metadata.
        """
        if not self.enabled:
            return

        data = {
            "type": "message",
            "content": text,
            "metadata": meta or {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        session_id = (meta or {}).get("session_id", to_handle)
        await _connection_manager.send_to_session(session_id, data)

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

        data = event.to_dict()
        data["metadata"] = {**(meta or {}), **data.get("metadata", {})}

        await _connection_manager.send_to_session(session_id, data)

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of stale connections."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await _connection_manager.cleanup_stale(self._connection_timeout)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in cleanup loop")

    async def start(self) -> None:
        """Start the web channel."""
        if not self.enabled:
            logger.debug("Web channel disabled")
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(),
            name="web_channel_cleanup",
        )
        logger.info("Web channel started")

    async def stop(self) -> None:
        """Stop the web channel."""
        if not self.enabled:
            return

        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Web channel stopped")

    async def health_check(self) -> dict[str, Any]:
        """Check channel health.

        Returns:
            Health status dictionary.
        """
        stats = _connection_manager.get_stats()
        return {
            "channel": self.channel_type.value,
            "enabled": self.enabled,
            "running": self._running,
            "healthy": self.enabled and self._running,
            **stats,
        }
